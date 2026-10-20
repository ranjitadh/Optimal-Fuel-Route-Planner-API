import math
from django.db import models
from shapely.geometry import LineString, Point

from routing.models import FuelStop
from routing.services.osrm import get_route

DEFAULT_MAX_RANGE_MILES = 500.0
DEFAULT_MPG = 10.0
DEFAULT_CORRIDOR_MILES = 10.0
DEFAULT_SAFETY_MARGIN_MILES = 25.0  # Reserve kept in the tank; usable range = max range - this.
DEFAULT_CLUSTER_MILES = 2.0         # Stations closer than this are treated as one interchange.
FUEL_STEP_GALLONS = 0.05            # Fuel discretization for the exact refueling DP.

# Project contract (see README "Problem Specifications & Vehicle Rules"):
#   tank_capacity_gallons = max_range_miles / mpg
# The vehicle is assumed to START WITH A FULL TANK. That initial fuel is already
# owned, so it is never billed as an en-route purchase.
FUEL_STOP_NOTE = "En-route refueling stop"


def _validate_positive_finite(value, name):
    if value is None:
        raise ValueError(f"{name} is required.")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def plan_refueling(total_distance_miles, mpg, max_range_miles, candidates,
                   safety_margin_miles=DEFAULT_SAFETY_MARGIN_MILES):
    """
    Minimum-cost refueling planner with partial fills and a tank capacity limit.

    Model
    -----
    * Starts with a FULL tank of ``tank_capacity_gallons = max_range_miles / mpg``.
    * ``usable_range_miles = max_range_miles - safety_margin_miles`` is the furthest
      the vehicle may drive between refuels (the reserve is never planned to be used).
    * At a stop the vehicle may buy ANY amount up to the free space in the tank.
    * Cost of a stop = purchased gallons x that station's price.

    Policy (exact dynamic program):
    nodes are the start (mile 0, full free tank), every candidate station, and the
    finish. Fuel is discretized at ``FUEL_STEP_GALLONS``; the DP state is
    (node, fuel-level) and stores the minimum purchase cost to reach it. At a station
    any amount up to the free tank space may be bought (partial fills allowed); a leg
    is allowed only if its distance is within ``usable_range_miles`` and the fuel in
    the tank covers it. The start node's fuel is free, so it is neither bought nor
    billed. This is exact up to the fuel discretization and is cross-checked against a
    brute-force reference in the test-suite.

    Returns a dict with ``fuel_stops`` plus unrounded ``total_purchased_gallons``
    and ``total_purchase_cost``. Raises ValueError when no feasible plan exists.
    """
    _validate_positive_finite(mpg, "mpg")
    _validate_positive_finite(max_range_miles, "max_range_miles")
    if safety_margin_miles < 0:
        raise ValueError("safety_margin_miles cannot be negative.")

    tank_capacity = max_range_miles / mpg
    usable_range = max_range_miles - safety_margin_miles
    if usable_range <= 0:
        raise ValueError(
            "usable range is not positive after applying the safety margin "
            f"({safety_margin_miles} mi on a {max_range_miles} mi tank)."
        )

    consumed_gallons = total_distance_miles / mpg

    # Stations strictly between start and finish, sorted by position along the route.
    usable = [c for c in candidates if 0.0 < c["route_mile"] < total_distance_miles]
    usable.sort(key=lambda c: c["route_mile"])

    # Trip reachable on the starting tank: zero mandatory stops, zero purchases.
    if total_distance_miles <= usable_range:
        return {
            "fuel_stops": [],
            "total_purchased_gallons": 0.0,
            "total_purchase_cost": 0.0,
            "tank_capacity_gallons": tank_capacity,
            "usable_range_miles": usable_range,
            "starting_fuel_gallons": tank_capacity,
            "consumed_gallons": consumed_gallons,
        }

    eps = 1e-9

    # ---- Exact DP over discretized fuel levels -----------------------------
    # Positions/indices: 0 = start, 1..n = stations, n+1 = finish.
    positions = [0.0] + [c["route_mile"] for c in usable] + [total_distance_miles]
    n_stations = len(usable)
    finish_index = n_stations + 1

    # Validate feasibility up front: no gap between consecutive refuel points may
    # exceed the usable range.
    for a, b in zip(positions, positions[1:]):
        if b - a > usable_range + 1e-6:
            raise ValueError(
                f"No feasible refueling plan: a {b - a:.1f} mi gap between refueling "
                f"opportunities exceeds the usable range of {usable_range:.1f} mi."
            )

    step = FUEL_STEP_GALLONS
    n_levels = int(math.floor(tank_capacity / step + 1e-9)) + 1  # 0..tank_capacity
    max_level = n_levels - 1
    inv_step = 1.0 / step

    INF = float("inf")
    # Dijkstra (label-setting) over states (node_index, fuel_level). Two edge kinds:
    #   * buy one fuel increment at a station: (i, l) -> (i, l+1)  cost = step*price
    #   * drive from i to j (within usable range): (i, l) -> (j, l')  cost = 0
    # The start holds a full free tank. This is exact up to the fuel discretization.
    dist = [[INF] * n_levels for _ in range(len(positions))]
    prev = [[None] * n_levels for _ in range(len(positions))]

    n_nodes = len(positions)
    # For every ordered node pair (i, j) within the usable range, precompute the
    # fuel the leg consumes in whole discretized levels. Consumption is rounded
    # UP (ceil) so a leg can never be driven on less fuel than it physically
    # needs; arrival is then lvl - needed, which floors the leftover and keeps
    # the plan feasible (no phantom fuel, never arrives with a negative tank).
    leg_levels = [None] * n_nodes  # leg_levels[i] = list of (j, fuel_levels_consumed)
    for i in range(n_nodes):
        bucket = []
        for j in range(i + 1, n_nodes):
            leg = positions[j] - positions[i]
            if leg > usable_range + 1e-6:
                break
            bucket.append((j, int(math.ceil(leg / mpg * inv_step - 1e-9))))
        leg_levels[i] = bucket

    start_level = max(0, min(max_level, int(round(tank_capacity * inv_step))))
    dist[0][start_level] = 0.0

    import heapq
    heap = [(0.0, 0, start_level)]

    while heap:
        cost, i, lvl = heapq.heappop(heap)
        if cost > dist[i][lvl] + 1e-12:
            continue

        # Buy one increment at a station.
        if 1 <= i <= n_stations and lvl < max_level:
            nc = cost + step * usable[i - 1]["retail_price"]
            if nc < dist[i][lvl + 1] - 1e-12:
                dist[i][lvl + 1] = nc
                prev[i][lvl + 1] = (i, lvl, True)
                heapq.heappush(heap, (nc, i, lvl + 1))

        # Drive to every later node within usable range.
        for j, needed in leg_levels[i]:
            if lvl < needed:
                continue
            jl = lvl - needed
            if cost < dist[j][jl] - 1e-12:
                dist[j][jl] = cost
                prev[j][jl] = (i, lvl, False)
                heapq.heappush(heap, (cost, j, jl))


    finish_index = len(positions) - 1
    best_level = min(range(n_levels), key=lambda lvl: dist[finish_index][lvl])
    if dist[finish_index][best_level] == INF:
        raise ValueError(
            "No feasible refueling plan: the destination cannot be reached with the "
            f"usable range of {usable_range:.1f} mi."
        )

    # Reconstruct: walk back to the start, keeping only buying steps at stations.
    raw = []  # (station_index, gallons) in reverse order
    i, lvl = finish_index, best_level
    steps = 0
    while prev[i][lvl] is not None:
        pi, plvl, was_buy = prev[i][lvl]
        if was_buy and 1 <= pi <= n_stations:
            raw.append((pi, step))
        i, lvl = pi, plvl
        steps += 1
        if steps > len(positions) * n_levels + 1:
            raise ValueError("No feasible refueling plan: optimizer failed to converge.")

    raw.reverse()
    purchases = {}
    order = []
    prev_purchase_position = 0.0
    for pi, buy_gal in raw:
        station = usable[pi - 1]
        _record_purchase(purchases, order, station, buy_gal, prev_purchase_position)
        prev_purchase_position = station["route_mile"]

    fuel_stops = [purchases[id(s)] for s in order]
    total_purchased = sum(s["gallons_filled"] for s in fuel_stops)
    total_cost = sum(s["cost_usd"] for s in fuel_stops)

    return {
        "fuel_stops": fuel_stops,
        "total_purchased_gallons": total_purchased,
        "total_purchase_cost": total_cost,
        "tank_capacity_gallons": tank_capacity,
        "usable_range_miles": usable_range,
        "starting_fuel_gallons": tank_capacity,
        "consumed_gallons": consumed_gallons,
    }


def _record_purchase(purchases, order, station, gallons, prev_position):
    """Accumulate a purchase at ``station`` (unrounded gallons and cost)."""
    key = id(station)
    if key not in purchases:
        purchases[key] = {
            "opis_id": station.get("opis_id"),
            "truckstop_name": station["truckstop_name"],
            "address": station["address"],
            "city": station["city"],
            "state": station["state"],
            "retail_price": station["retail_price"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "route_mile": station["route_mile"],
            "leg_distance_miles": round(station["route_mile"] - prev_position, 1),
            "gallons_filled": 0.0,
            "cost_usd": 0.0,
            "note": FUEL_STOP_NOTE,
        }
        order.append(station)
    purchases[key]["gallons_filled"] += gallons
    purchases[key]["cost_usd"] += gallons * station["retail_price"]


def optimize_fuel_route(
    start_coords: tuple[float, float],
    finish_coords: tuple[float, float],
    max_range_miles: float = DEFAULT_MAX_RANGE_MILES,
    mpg: float = DEFAULT_MPG,
    corridor_miles: float = DEFAULT_CORRIDOR_MILES,
) -> dict:
    """
    Computes a driving route and the cost-optimal refueling stops along it.

    Assumes the vehicle starts with a full tank; only fuel purchased at stations
    is billed. Guarantees no leg between refuels exceeds the usable range
    (max range minus the safety margin), and that no single purchase exceeds the
    tank capacity.
    """
    _validate_positive_finite(max_range_miles, "max_range_miles")
    _validate_positive_finite(mpg, "mpg")

    route_data = get_route(start_coords, finish_coords)
    total_distance = route_data["distance_miles"]
    coords = route_data["coordinates"]  # [[lon, lat], ...]

    # Planar projection to convert degrees into exact Euclidean miles.
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    mean_lat = sum(lats) / len(lats)
    cos_factor = math.cos(math.radians(mean_lat))
    min_lon = min(lons)
    min_lat = min(lats)

    def to_miles_xy(lon, lat):
        return ((lon - min_lon) * 69.0 * cos_factor, (lat - min_lat) * 69.0)

    line = LineString([to_miles_xy(c[0], c[1]) for c in coords])

    bbox_stops = list(
        FuelStop.objects.filter(
            latitude__range=(min(lats) - 0.3, max(lats) + 0.3),
            longitude__range=(min(lons) - 0.3, max(lons) + 0.3),
        )
    )

    candidates = []
    for s in bbox_stops:
        price = float(s.retail_price) if s.retail_price is not None else None
        if price is None or price <= 0:
            continue  # missing/invalid price -> unusable station
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
                    "retail_price": price,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "route_mile": round(route_mile, 1),
                    "dist_to_route": round(dist_to_route, 1),
                })

    candidates.sort(key=lambda x: x["route_mile"])

    # Cluster stations within DEFAULT_CLUSTER_MILES, keeping the lowest price.
    clustered = []
    for c in candidates:
        if not clustered or (c["route_mile"] - clustered[-1]["route_mile"]) >= DEFAULT_CLUSTER_MILES:
            clustered.append(c)
        elif c["retail_price"] < clustered[-1]["retail_price"]:
            clustered[-1] = c

    plan = plan_refueling(
        total_distance_miles=total_distance,
        mpg=mpg,
        max_range_miles=max_range_miles,
        candidates=clustered,
        safety_margin_miles=DEFAULT_SAFETY_MARGIN_MILES,
    )

    stops = plan["fuel_stops"]
    total_purchased = plan["total_purchased_gallons"]
    total_cost = plan["total_purchase_cost"]
    consumed = plan["consumed_gallons"]

    # Optional (unbilled) suggestion for trips covered by the starting tank.
    suggested_stop = None
    if not stops and clustered:
        suggestion = min(clustered, key=lambda c: c["retail_price"])
        suggested_stop = {
            "truckstop_name": suggestion["truckstop_name"],
            "city": suggestion["city"],
            "state": suggestion["state"],
            "retail_price": suggestion["retail_price"],
            "route_mile": suggestion["route_mile"],
        }

    displayed_stops = [_display_stop(s) for s in stops]
    avg_price = (total_cost / total_purchased) if total_purchased > 0 else None

    return {
        "total_distance_miles": total_distance,
        "duration_hours": route_data["duration_hours"],
        "total_fuel_gallons": round(total_purchased, 2),
        "total_fuel_consumed_gallons": round(consumed, 2),
        "total_fuel_cost_usd": round(total_cost, 2),
        "avg_price_per_gallon": round(avg_price, 4) if avg_price is not None else None,
        "tank_capacity_gallons": round(plan["tank_capacity_gallons"], 2),
        "usable_range_miles": round(plan["usable_range_miles"], 1),
        "starting_fuel_gallons": round(plan["starting_fuel_gallons"], 2),
        "fuel_stops_count": len(stops),
        "fuel_stops": displayed_stops,
        "suggested_stop": suggested_stop,
        "route_geometry": route_data["geojson"],
    }


def _display_stop(stop: dict) -> dict:
    """Rounded, API-safe view of a single refueling stop."""
    return {
        "opis_id": stop.get("opis_id"),
        "truckstop_name": stop["truckstop_name"],
        "address": stop["address"],
        "city": stop["city"],
        "state": stop["state"],
        "retail_price": round(stop["retail_price"], 3),
        "latitude": stop["latitude"],
        "longitude": stop["longitude"],
        "route_mile": stop["route_mile"],
        "leg_distance_miles": stop["leg_distance_miles"],
        "gallons_filled": round(stop["gallons_filled"], 2),
        "cost_usd": round(stop["cost_usd"], 2),
        "note": stop.get("note"),
    }
