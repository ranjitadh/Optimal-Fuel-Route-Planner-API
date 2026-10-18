import pytest
from routing.services.optimizer import optimize_fuel_route

@pytest.mark.django_db
def test_optimizer_short_trip():
    # NYC to Philadelphia (~95 miles, well below 500-mile max range)
    nyc = (40.7128, -74.0060)
    philly = (39.9526, -75.1652)
    res = optimize_fuel_route(nyc, philly, max_range_miles=500.0, mpg=10.0)
    
    assert res["total_distance_miles"] < 500.0
    assert res["total_fuel_gallons"] == pytest.approx(res["total_distance_miles"] / 10.0, rel=1e-2)
    assert res["total_fuel_cost_usd"] >= 0.0
    # On trips <= 500 miles, either 0 mandatory stops or 1 optional stop
    assert res["fuel_stops_count"] in (0, 1)

@pytest.mark.django_db
def test_optimizer_long_trip_respects_500_mile_range():
    # NYC to Chicago (~790 miles, exceeds 500-mile max range)
    nyc = (40.7128, -74.0060)
    chicago = (41.8781, -87.6298)
    res = optimize_fuel_route(nyc, chicago, max_range_miles=500.0, mpg=10.0)

    assert res["total_distance_miles"] > 500.0
    assert res["total_fuel_gallons"] == pytest.approx(res["total_distance_miles"] / 10.0, rel=1e-2)
    assert res["total_fuel_cost_usd"] > 0.0
    assert res["fuel_stops_count"] >= 1

    # Verify that the vehicle never travels more than 500 miles without refueling
    stops = res["fuel_stops"]
    prev_mile = 0.0
    for stop in stops:
        hop = stop["route_mile"] - prev_mile
        assert hop <= 500.0, f"Hop of {hop} miles exceeds 500-mile range!"
        prev_mile = stop["route_mile"]

    final_hop = res["total_distance_miles"] - prev_mile
    assert final_hop <= 500.0, f"Final leg of {final_hop} miles exceeds 500-mile range!"
