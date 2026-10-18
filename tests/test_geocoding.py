import pytest
from routing.services.geocoding import geocode_location

def test_geocode_valid_us_city():
    res = geocode_location("Chicago, IL")
    assert "latitude" in res
    assert "longitude" in res
    assert 41.0 <= res["latitude"] <= 43.0
    assert -88.5 <= res["longitude"] <= -87.0
    assert res["country_code"] == "us"

def test_geocode_coordinates_input():
    res = geocode_location("40.7128, -74.0060")
    assert abs(res["latitude"] - 40.7128) < 1e-4
    assert abs(res["longitude"] - (-74.0060)) < 1e-4

def test_geocode_invalid_location_raises():
    with pytest.raises(ValueError, match="Could not resolve|outside"):
        geocode_location("NonExistentCityXYZ123456789")

def test_geocode_international_location_rejected():
    with pytest.raises(ValueError, match="outside the USA|Could not resolve"):
        geocode_location("Tokyo, Japan")
