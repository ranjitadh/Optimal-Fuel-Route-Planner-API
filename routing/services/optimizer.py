import math
from decimal import Decimal
from shapely.geometry import LineString, Point
from routing.models import FuelStop
from routing.services.osrm import get_route

DEFAULT_MAX_RANGE_MILES = 500.0
DEFAULT_MPG = 10.0
DEFAULT_CORRIDOR_MILES = 10.0
DEFAULT_SAFETY_MARGIN_MILES = 25.0  # Plan refuels before reaching 475 miles on a 500-mile tank

def optimize_fuel_route(
    start_coords: tuple[float, float],
    finish_coords: tuple[float, float],
    max_range_miles: float = DEFAULT_MAX_RANGE_MILES,
    mpg: float = DEFAULT_MPG,
    corridor_miles: float = DEFAULT_CORRIDOR_MILES,
) -> dict:
    """
    Computes driving route and cost-optimal fuel stops along the route.
    Guarantees that the vehicle never exceeds the maximum tank range (500 miles).
    """
    route_data = get_route(start_coords, finish_coords)
    total_distance = route_data["distance_miles"]
    coords = route_data["coordinates"]  # [[lon, lat], ...]

    # Planar projection to convert degrees into exact Euclidean miles
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    mean_lat = sum(lats) / len(lats)
    cos_factor = math.cos(math.radians(mean_lat))
    min_lon = min(lons)
    min_lat = min(lats)

    def to_miles_xy(lon, lat):
        return ((lon - min_lon) * 69.0 * cos_factor, (lat - min_lat) * 69.0)

    xy_route = [to_miles_xy(c[0], c[1]) for c in coords]
    line = LineString(xy_route)

    # Query bounding box of fuel stops with buffer
    bbox_stops = list(
        FuelStop.objects.filter(
            latitude__range=(min(lats) - 0.3, max(lats) + 0.3),
            longitude__range=(min(lons) - 0.3, max(lons) + 0.3),
        )
    )

    candidates = []
    for s in bbox_stops:
        p = Point(to_miles_xy(s.longitude, s.latitude))
        dist_to_route = line.distance(p)
        if dist_to_route <= corridor_miles:
            route_mile = line.project(p)
            if 0 < route_mile < total_distance:
                candidates.append({
                    "opis_id": s.opis_id,
                    "truckstop_name": s.truckstop_name,
                    "address": s.address,
                    "city": s.city,
                    "state": s.state,
                    "rack_id": s.rack_id,
                    "retail_price": float(s.retail_price),
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "route_mile": round(route_mile, 1),
                    "dist_to_route": round(dist_to_route, 1),
                })

    candidates.sort(key=lambda x: x["route_mile"])

    # Cluster stations that are within 2 miles of each other, keeping the lowest price
    clustered = []
    for c in candidates:
        if not clustered or (c["route_mile"] - clustered[-1]["route_mile"]) >= 2.0:
            clustered.append(c)
        elif c["retail_price"] < clustered[-1]["retail_price"]:
            clustered[-1] = c

    total_gallons_consumed = round(total_distance / mpg, 2)

    # Case 1: Trip is <= max_range_miles (500 miles)
    if total_distance <= max_range_miles:
        # Trip can physically be done on 1 full tank
        fuel_stops = []
        if clustered:
            best_stop = min(clustered, key=lambda x: x["retail_price"])
            cost = round(total_gallons_consumed * best_stop["retail_price"], 2)
            fuel_stops.append({
                **best_stop,
                "leg_distance_miles": round(best_stop["route_mile"], 1),
                "gallons_filled": total_gallons_consumed,
                "cost_usd": cost,
                "note": "Optional optimal refueling stop along route (trip within 500-mile vehicle range)",
            })
            total_fuel_cost = cost
        else:
            total_fuel_cost = 0.0

        return {
            "total_distance_miles": total_distance,
            "duration_hours": route_data["duration_hours"],
            "total_fuel_gallons": total_gallons_consumed,
            "total_fuel_cost_usd": total_fuel_cost,
            "fuel_stops_count": len(fuel_stops),
            "fuel_stops": fuel_stops,
            "route_geometry": route_data["geojson"],
        }

    # Case 2: Trip > max_range_miles (requires one or multiple fuel stops)
    curr_mile = 0.0
    fuel_stops = []
    total_fuel_cost = 0.0
    effective_range = max_range_miles - DEFAULT_SAFETY_MARGIN_MILES  # 475 miles

    while curr_mile + max_range_miles < total_distance:
        max_reach = curr_mile + effective_range
        # Preferred window: between 250 miles and max_reach for well-spaced stops
        pref_min = curr_mile + 250.0
        window = [c for c in clustered if pref_min <= c["route_mile"] <= max_reach]
        
        # If no station in preferred window, expand window down to curr_mile + 30
        if not window:
            window = [c for c in clustered if curr_mile + 30.0 <= c["route_mile"] <= max_reach]

        # If still no station, look for any station ahead within max_reach
        if not window:
            window = [c for c in clustered if curr_mile < c["route_mile"] <= curr_mile + max_range_miles]

        # Emergency fallback: pick nearest station ahead
        if not window:
            ahead = [c for c in clustered if c["route_mile"] > curr_mile]
            if not ahead:
                break
            best = ahead[0]
        else:
            # Pick the most cost-effective station in the window
            best = min(window, key=lambda x: x["retail_price"])

        leg_distance = round(best["route_mile"] - curr_mile, 1)
        leg_gallons = round(leg_distance / mpg, 2)
        step_cost = round(leg_gallons * best["retail_price"], 2)
        total_fuel_cost += step_cost

        fuel_stops.append({
            "opis_id": best["opis_id"],
            "truckstop_name": best["truckstop_name"],
            "address": best["address"],
            "city": best["city"],
            "state": best["state"],
            "retail_price": best["retail_price"],
            "latitude": best["latitude"],
            "longitude": best["longitude"],
            "route_mile": best["route_mile"],
            "leg_distance_miles": leg_distance,
            "gallons_filled": leg_gallons,
            "cost_usd": step_cost,
        })

        curr_mile = best["route_mile"]

    # Final leg to destination
    final_leg_distance = round(total_distance - curr_mile, 1)
    final_leg_gallons = round(final_leg_distance / mpg, 2)
    # The fuel for the final leg was purchased at the last stop
    last_stop_price = fuel_stops[-1]["retail_price"] if fuel_stops else 3.50
    final_step_cost = round(final_leg_gallons * last_stop_price, 2)
    total_fuel_cost += final_step_cost

    # Update the last stop's gallons and cost to include completing the trip
    if fuel_stops:
        fuel_stops[-1]["gallons_filled"] = round(fuel_stops[-1]["gallons_filled"] + final_leg_gallons, 2)
        fuel_stops[-1]["cost_usd"] = round(fuel_stops[-1]["cost_usd"] + final_step_cost, 2)

    return {
        "total_distance_miles": total_distance,
        "duration_hours": route_data["duration_hours"],
        "total_fuel_gallons": total_gallons_consumed,
        "total_fuel_cost_usd": round(total_fuel_cost, 2),
        "fuel_stops_count": len(fuel_stops),
        "fuel_stops": fuel_stops,
        "route_geometry": route_data["geojson"],
    }
