import math
import requests

METERS_TO_MILES = 0.000621371

def haversine_miles(lat1, lon1, lat2, lon2):
    """Computes great-circle distance between two points on Earth in miles."""
    r = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c

def get_route(start_coords: tuple[float, float], finish_coords: tuple[float, float]) -> dict:
    """
    Fetches driving route from OSRM between start (lat, lon) and finish (lat, lon).
    Returns total distance in miles, duration, route geometry coordinates,
    and cumulative miles along the route polyline.
    """
    start_lat, start_lon = start_coords
    finish_lat, finish_lon = finish_coords

    # OSRM expects coordinates in order: lon,lat
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{start_lon:.6f},{start_lat:.6f};{finish_lon:.6f},{finish_lat:.6f}"
        f"?overview=full&geometries=geojson"
    )

    headers = {
        "User-Agent": "FuelRoutePlanner/1.0",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise ValueError(f"OSRM Routing service failed: {str(e)}")

    if data.get("code") != "Ok" or not data.get("routes"):
        msg = data.get("message", "No driving route found between specified points.")
        raise ValueError(f"Routing error: {msg}")

    route = data["routes"][0]
    distance_meters = route["distance"]
    total_distance_miles = distance_meters * METERS_TO_MILES
    duration_hours = route["duration"] / 3600.0

    raw_coords = route["geometry"]["coordinates"]  # [[lon, lat], ...]

    # Compute cumulative distances along the route polyline
    cum_distances = [0.0]
    total_haversine = 0.0

    for i in range(1, len(raw_coords)):
        prev_lon, prev_lat = raw_coords[i - 1]
        curr_lon, curr_lat = raw_coords[i]
        seg_dist = haversine_miles(prev_lat, prev_lon, curr_lat, curr_lon)
        total_haversine += seg_dist
        cum_distances.append(total_haversine)

    # Scale cumulative distances so the final point matches OSRM's road network distance
    if total_haversine > 0:
        scale = total_distance_miles / total_haversine
        cum_distances = [d * scale for d in cum_distances]
        cum_distances[-1] = total_distance_miles

    return {
        "distance_miles": round(total_distance_miles, 2),
        "duration_hours": round(duration_hours, 2),
        "coordinates": raw_coords,
        "cum_distances": cum_distances,
        "geojson": route["geometry"],
    }
