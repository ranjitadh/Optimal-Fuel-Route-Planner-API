import pytest
from routing.services.optimizer import optimize_fuel_route

@pytest.mark.django_db
def test_optimizer_short_trip():
    # NYC to Philadelphia (~95 miles, well below the 475-mile usable range)
    nyc = (40.7128, -74.0060)
    philly = (39.9526, -75.1652)
    res = optimize_fuel_route(nyc, philly, max_range_miles=500.0, mpg=10.0)

    assert res["total_distance_miles"] < 475.0
    # The vehicle starts with a full tank, so a trip within usable range needs
    # no mandatory refueling and incurs no purchase cost.
    assert res["total_fuel_gallons"] == 0.0
    assert res["total_fuel_cost_usd"] == 0.0
    assert res["fuel_stops_count"] == 0
    # Consumed fuel is still reported (distance / mpg).
    assert res["total_fuel_consumed_gallons"] == pytest.approx(
        res["total_distance_miles"] / 10.0, rel=1e-2
    )


@pytest.mark.django_db
def test_optimizer_long_trip_respects_500_mile_range():
    # NYC to Chicago (~790 miles, exceeds the 475-mile usable range)
    nyc = (40.7128, -74.0060)
    chicago = (41.8781, -87.6298)
    res = optimize_fuel_route(nyc, chicago, max_range_miles=500.0, mpg=10.0)

    assert res["total_distance_miles"] > 475.0
    # Only fuel beyond the free starting tank is purchased. The DP discretizes fuel,
    # so allow a small tolerance around (consumed - tank capacity).
    expected_purchase = res["total_distance_miles"] / 10.0 - 50.0
    assert res["total_fuel_gallons"] == pytest.approx(expected_purchase, abs=0.5)
    assert res["total_fuel_cost_usd"] > 0.0
    assert res["fuel_stops_count"] >= 1
    # Fuel drawn from the free starting tank can never exceed the tank capacity.
    assert res["total_fuel_consumed_gallons"] - res["total_fuel_gallons"] <= 50.0 + 1e-6

    # Every reported leg must be driveable on the fuel bought up to that point.
    stops = res["fuel_stops"]
    prev_mile = 0.0
    fuel = 50.0  # start with a full tank
    for stop in stops:
        leg_gal = (stop["route_mile"] - prev_mile) / 10.0
        fuel -= leg_gal
        assert fuel >= -1e-6, f"Ran out of fuel before mile {stop['route_mile']}!"
        hop = stop["route_mile"] - prev_mile
        assert hop <= 475.0 + 1e-6, f"Hop of {hop} miles exceeds the usable range!"
        fuel += stop["gallons_filled"]
        assert fuel <= 50.0 + 1e-6, f"Tank overflow at mile {stop['route_mile']}!"
        prev_mile = stop["route_mile"]

    final_hop = res["total_distance_miles"] - prev_mile
    assert final_hop <= 475.0 + 1e-6, f"Final leg of {final_hop} miles exceeds the usable range!"
    assert fuel - final_hop / 10.0 >= -1e-6, "Ran out of fuel before the destination!"
