import re
import urllib.parse
import requests

# In-memory geocoding cache to speed up repeated queries and respect rate limits
_GEOCODE_CACHE = {}

def geocode_location(query: str) -> dict:
    """
    Geocodes an input location string (city/state, address, or 'lat,lon' coordinates)
    and verifies that it is within the USA.
    """
    query_str = query.strip()
    if not query_str:
        raise ValueError("Location query cannot be empty.")

    # Check cache first
    cache_key = query_str.lower()
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    # Check if query is numeric coordinates "lat, lon" or "lat,lon"
    coord_match = re.match(
        r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$",
        query_str,
    )
    if coord_match:
        parts = [float(p.strip()) for p in query_str.split(",")]
        lat, lon = parts[0], parts[1]
        # Continental US + Alaska + Hawaii bounds
        is_in_us = (24.0 <= lat <= 72.0) and (-180.0 <= lon <= -65.0)
        if not is_in_us:
            raise ValueError(f"Coordinates ({lat}, {lon}) are outside the USA.")

        res = {
            "latitude": lat,
            "longitude": lon,
            "display_name": f"{lat:.4f}, {lon:.4f}",
            "country_code": "us",
        }
        _GEOCODE_CACHE[cache_key] = res
        return res

    # Use Nominatim API for geocoding with address details
    url = (
        f"https://nominatim.openstreetmap.org/search?"
        f"q={urllib.parse.quote(query_str)}&format=json&addressdetails=1&limit=1"
    )
    headers = {
        "User-Agent": "FuelRoutePlanner/1.0 (contact: support@fuelrouteplanner.local)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise ValueError(f"Geocoding service unavailable for '{query_str}': {str(e)}")

    if not data:
        raise ValueError(f"Could not resolve location '{query_str}'.")

    item = data[0]
    lat = float(item["lat"])
    lon = float(item["lon"])
    display_name = item.get("display_name", query_str)
    country_code = item.get("address", {}).get("country_code", "").lower()

    # Reject non-US locations
    if country_code and country_code != "us":
        raise ValueError(f"Location '{query_str}' is in '{country_code.upper()}', outside the USA.")

    # Validate US bounding box
    is_in_us = (24.0 <= lat <= 72.0) and (-180.0 <= lon <= -65.0)
    if not is_in_us:
        raise ValueError(f"Location '{query_str}' ({display_name}) is outside the USA.")

    result = {
        "latitude": lat,
        "longitude": lon,
        "display_name": display_name,
        "country_code": "us",
    }
    _GEOCODE_CACHE[cache_key] = result
    return result
