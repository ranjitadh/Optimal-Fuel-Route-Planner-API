import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
import django
django.setup()

from rest_framework.test import APIClient
from routing.services.optimizer import optimize_fuel_route
from routing.services.geocoding import geocode_location

client = APIClient()

test_cases = [
    # 1. Short Trips (< 500 miles)
    {
        "category": "Short Route (< 500 mi)",
        "start": "New York, NY",
        "finish": "Philadelphia, PA",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "0 (Optional 1)",
    },
    {
        "category": "Short Route (< 500 mi)",
        "start": "Los Angeles, CA",
        "finish": "San Diego, CA",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "0 (Optional 1)",
    },
    {
        "category": "Short Route (< 500 mi)",
        "start": "Dallas, TX",
        "finish": "Houston, TX",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "0 (Optional 1)",
    },
    # 2. Medium Trips (500 - 1000 miles)
    {
        "category": "Medium Route (500-1000 mi)",
        "start": "New York, NY",
        "finish": "Chicago, IL",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "1 - 2 stops",
    },
    {
        "category": "Medium Route (500-1000 mi)",
        "start": "Atlanta, GA",
        "finish": "Miami, FL",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "1 - 2 stops",
    },
    # 3. Long Cross-Country Trips (> 2000 miles)
    {
        "category": "Long Cross-Country (> 2000 mi)",
        "start": "New York, NY",
        "finish": "Los Angeles, CA",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "5 - 7 stops",
    },
    {
        "category": "Long Cross-Country (> 2000 mi)",
        "start": "Seattle, WA",
        "finish": "Miami, FL",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "6 - 9 stops",
    },
    # 4. Custom Specs (Altered Range & MPG)
    {
        "category": "Custom Range / MPG",
        "start": "Chicago, IL",
        "finish": "Atlanta, GA",
        "max_range": 350.0,
        "mpg": 15.0,
        "expected_stops": "1 - 3 stops",
    },
    # 5. Coordinate Inputs
    {
        "category": "Raw Coordinates",
        "start": "40.7128,-74.0060",
        "finish": "41.8781,-87.6298",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "1 - 2 stops",
    },
    # 6. Edge Cases & Validation
    {
        "category": "Edge Case: Invalid Name",
        "start": "NonExistentFictionalTownXYZ123",
        "finish": "Chicago, IL",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "Error 400",
    },
    {
        "category": "Edge Case: International",
        "start": "Paris, France",
        "finish": "New York, NY",
        "max_range": 500.0,
        "mpg": 10.0,
        "expected_stops": "Error 400",
    },
    {
        "category": "Endpoint: Map HTML",
        "start": "Boston, MA",
        "finish": "Washington, DC",
        "type": "map_html",
        "expected_stops": "HTML 200 OK",
    },
    {
        "category": "Endpoint: Fuel Stops Query",
        "query": "/api/fuel-stops/?state=OH&max_price=3.05",
        "type": "fuel_stops_api",
        "expected_stops": "Paginated 200 OK",
    },
    {
        "category": "Endpoint: Health Check",
        "query": "/api/health/",
        "type": "health",
        "expected_stops": "Healthy 200 OK",
    },
]

results = []

for tc in test_cases:
    t0 = time.time()
    cat = tc["category"]
    
    # Special endpoints
    if tc.get("type") == "map_html":
        resp = client.get(f"/api/route/map/?start={tc['start']}&finish={tc['finish']}")
        elapsed = round(time.time() - t0, 2)
        passed = (resp.status_code == 200) and ("html" in resp["Content-Type"])
        results.append({
            "test_case": f"Map HTML View: {tc['start']} -> {tc['finish']}",
            "category": cat,
            "status_code": resp.status_code,
            "distance": "N/A",
            "stops": "Renders Leaflet Map",
            "fuel_gal": "N/A",
            "total_cost": "N/A",
            "max_leg": "<= 500 mi",
            "latency": f"{elapsed}s",
            "verdict": "PASSED" if passed else "FAILED",
        })
        continue

    if tc.get("type") == "fuel_stops_api":
        resp = client.get(tc["query"])
        elapsed = round(time.time() - t0, 2)
        data = resp.json()
        passed = (resp.status_code == 200) and ("results" in data) and len(data["results"]) > 0
        results.append({
            "test_case": f"Fuel Stops Query: {tc['query']}",
            "category": cat,
            "status_code": resp.status_code,
            "distance": "N/A",
            "stops": f"{len(data.get('results', []))} stations",
            "fuel_gal": "N/A",
            "total_cost": "N/A",
            "max_leg": "N/A",
            "latency": f"{elapsed}s",
            "verdict": "PASSED" if passed else "FAILED",
        })
        continue

    if tc.get("type") == "health":
        resp = client.get(tc["query"])
        elapsed = round(time.time() - t0, 2)
        data = resp.json()
        passed = (resp.status_code == 200) and (data.get("status") == "healthy")
        results.append({
            "test_case": "System Health Check",
            "category": cat,
            "status_code": resp.status_code,
            "distance": "N/A",
            "stops": f"{data.get('fuel_stops_count', 0)} stops in DB",
            "fuel_gal": "N/A",
            "total_cost": "N/A",
            "max_leg": "N/A",
            "latency": f"{elapsed}s",
            "verdict": "PASSED" if passed else "FAILED",
        })
        continue

    # Standard Route API call
    payload = {
        "start": tc["start"],
        "finish": tc["finish"],
        "max_range": tc.get("max_range", 500.0),
        "mpg": tc.get("mpg", 10.0),
    }

    resp = client.post("/api/route/", data=payload, format="json")
    elapsed = round(time.time() - t0, 2)

    # Check for expected error cases
    if "Error" in tc["expected_stops"]:
        passed = resp.status_code == 400
        detail = resp.json().get("detail", "Error caught as expected")
        results.append({
            "test_case": f"{tc['start']} -> {tc['finish']}",
            "category": cat,
            "status_code": resp.status_code,
            "distance": "N/A",
            "stops": "Rejected (Invalid)",
            "fuel_gal": "N/A",
            "total_cost": "N/A",
            "max_leg": "N/A",
            "latency": f"{elapsed}s",
            "verdict": "PASSED" if passed else "FAILED",
        })
        continue

    # Success case
    if resp.status_code == 200:
        data = resp.json()
        dist = data["total_distance_miles"]
        gal = data["total_fuel_gallons"]
        cost = data["total_fuel_cost_usd"]
        stops = data["fuel_stops"]
        stops_count = data["fuel_stops_count"]

        # Calculate max hop
        max_hop = 0.0
        prev_m = 0.0
        for s in stops:
            hop = s["route_mile"] - prev_m
            if hop > max_hop:
                max_hop = hop
            prev_m = s["route_mile"]
        final_hop = dist - prev_m
        if final_hop > max_hop:
            max_hop = final_hop

        range_respected = max_hop <= (tc.get("max_range", 500.0) + 0.1)
        gallons_correct = abs(gal - round(dist / tc.get("mpg", 10.0), 2)) < 0.2
        passed = range_respected and gallons_correct and cost > 0

        results.append({
            "test_case": f"{tc['start']} -> {tc['finish']}",
            "category": cat,
            "status_code": resp.status_code,
            "distance": f"{dist:.1f} mi",
            "stops": f"{stops_count} stop(s)",
            "fuel_gal": f"{gal:.1f} gal",
            "total_cost": f"${cost:.2f}",
            "max_leg": f"{max_hop:.1f} mi (<= {tc.get('max_range', 500.0)} mi)",
            "latency": f"{elapsed}s",
            "verdict": "PASSED" if passed else "FAILED",
        })
    else:
        results.append({
            "test_case": f"{tc['start']} -> {tc['finish']}",
            "category": cat,
            "status_code": resp.status_code,
            "distance": "ERROR",
            "stops": str(resp.json()),
            "fuel_gal": "ERROR",
            "total_cost": "ERROR",
            "max_leg": "ERROR",
            "latency": f"{elapsed}s",
            "verdict": "FAILED",
        })

print(json.dumps(results, indent=2))
