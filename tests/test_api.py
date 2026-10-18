import pytest
from rest_framework.test import APIClient

@pytest.fixture
def client():
    return APIClient()

@pytest.mark.django_db
def test_health_check(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["fuel_stops_count"] > 0

@pytest.mark.django_db
def test_route_optimization_api_get(client):
    response = client.get("/api/route/?start=New+York,+NY&finish=Philadelphia,+PA")
    assert response.status_code == 200
    data = response.json()
    assert "total_distance_miles" in data
    assert "total_fuel_gallons" in data
    assert "total_fuel_cost_usd" in data
    assert "fuel_stops" in data
    assert "map_url" in data
    assert data["total_fuel_gallons"] == pytest.approx(data["total_distance_miles"] / 10.0, rel=1e-2)

@pytest.mark.django_db
def test_route_optimization_api_post(client):
    payload = {
        "start": "Austin, TX",
        "finish": "Dallas, TX",
        "max_range": 500.0,
        "mpg": 10.0,
    }
    response = client.post("/api/route/", data=payload, format="json")
    assert response.status_code == 200
    data = response.json()
    assert data["total_distance_miles"] > 150.0
    assert data["total_fuel_cost_usd"] > 0.0

@pytest.mark.django_db
def test_route_map_endpoint_returns_html(client):
    response = client.get("/api/route/map/?start=New+York,+NY&finish=Boston,+MA")
    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    content = response.content.decode("utf-8")
    assert "leaflet" in content.lower() or "folium" in content.lower()

@pytest.mark.django_db
def test_fuel_stops_list_api(client):
    response = client.get("/api/fuel-stops/?state=OH")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0
    assert all(item["state"] == "OH" for item in data["results"])
