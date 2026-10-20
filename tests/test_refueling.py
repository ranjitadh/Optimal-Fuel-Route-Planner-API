"""
Unit tests for the minimum-cost refueling planner ``plan_refueling``.

These tests exercise the algorithm in isolation (no database, no routing) with
synthetic stations, and cross-check the exact dynamic program against a
brute-force reference on small inputs.
"""
import math
import random

import pytest

from routing.services.optimizer import (
    plan_refueling,
    DEFAULT_SAFETY_MARGIN_MILES,
)


def _station(route_mile, price, name=None):
    return {
        "opis_id": int(route_mile),
        "truckstop_name": name or f"STOP{route_mile}",
        "address": "I-00",
        "city": "City",
        "state": "ST",
        "retail_price": price,
        "latitude": 0.0,
        "longitude": 0.0,
        "route_mile": float(route_mile),
    }


def _brute_force_cost(total_distance, mpg, max_range, stations, margin, step=0.05):
    """Discretized reference: minimum purchase cost, allowing partial fills."""
    usable = max_range - margin
    tank = max_range / mpg
    nodes = sorted(s["route_mile"] for s in stations)
    prices = {s["route_mile"]: s["retail_price"] for s in stations}
    pts = [0.0] + nodes + [total_distance]
    n_levels = int(round(tank / step)) + 1
    INF = float("inf")
    dp = [[INF] * n_levels for _ in pts]
    dp[0][n_levels - 1] = 0.0
    for i in range(len(pts)):
        for fi in range(n_levels):
            cur = dp[i][fi]
            if cur == INF:
                continue
            fuel = fi * step
            buys = [0.0]
            if 1 <= i <= len(nodes):
                k = 0.0
                while k <= tank - fuel + 1e-9:
                    buys.append(k)
                    k += step
            for b in buys:
                nf = fuel + b
                for j in range(i + 1, len(pts)):
                    dist = pts[j] - pts[i]
                    if dist > usable + 1e-9:
                        break
                    rem = nf - dist / mpg
                    if rem < -1e-9:
                        continue
                    jl = int(round(max(rem, 0.0) / step))
                    nc = cur + b * prices.get(pts[i], 0.0)
                    if nc < dp[j][jl]:
                        dp[j][jl] = nc
    return min(dp[-1])


def test_short_trip_needs_no_purchase():
    """A trip within the usable range runs entirely on the free starting tank."""
    res = plan_refueling(
        total_distance_miles=300.0,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[_station(150, 3.5)],
    )
    assert res["total_purchased_gallons"] == 0.0
    assert res["total_purchase_cost"] == 0.0
    assert res["fuel_stops"] == []
    assert res["consumed_gallons"] == pytest.approx(30.0)
    assert res["starting_fuel_gallons"] == 50.0
    assert res["tank_capacity_gallons"] == 50.0
    assert res["usable_range_miles"] == 475.0


def test_only_fuel_beyond_starting_tank_is_purchased():
    """Consumed = distance/mpg but only (consumed - tank) is ever bought."""
    res = plan_refueling(
        total_distance_miles=790.51,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[
            _station(63.3, 3.079),
            _station(396.9, 3.059),
            _station(553.8, 3.009),
        ],
    )
    # Free fuel covers the first tank; the rest is bought at some station.
    assert res["consumed_gallons"] == pytest.approx(79.051)
    assert res["total_purchased_gallons"] == pytest.approx(79.051 - 50.0, abs=0.5)
    assert res["total_purchase_cost"] > 0.0


def test_partial_fill_uses_the_cheaper_station():
    """The planner tops up only enough to reach the cheaper station downstream."""
    res = plan_refueling(
        total_distance_miles=1200.0,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[
            _station(100, 3.0),
            _station(400, 3.5),
            _station(700, 2.9),
            _station(1000, 3.2),
        ],
    )
    # Optimal cost is 10@3.0 + 10@3.5 + 50@2.9 = 210.
    assert res["total_purchase_cost"] == pytest.approx(210.0, abs=1.0)
    bought = {s["route_mile"]: s["gallons_filled"] for s in res["fuel_stops"]}
    assert 100 in bought and 700 in bought  # uses both cheap stations


def test_no_single_purchase_exceeds_tank_capacity():
    res = plan_refueling(
        total_distance_miles=1600.0,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[_station(m, 3.0) for m in range(100, 1600, 100)],
    )
    tank = 50.0
    for stop in res["fuel_stops"]:
        assert stop["gallons_filled"] <= tank + 1e-6
    assert res["total_purchase_cost"] > 0.0


def test_reserve_is_respected_between_refuels():
    """No leg may exceed the usable range (max range - safety margin)."""
    usable = 500.0 - DEFAULT_SAFETY_MARGIN_MILES
    res = plan_refueling(
        total_distance_miles=1000.0,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[_station(450, 2.9), _station(900, 3.1)],
    )
    prev = 0.0
    for stop in res["fuel_stops"]:
        assert stop["route_mile"] - prev <= usable + 1e-6
        prev = stop["route_mile"]
    assert 1000.0 - prev <= usable + 1e-6


def test_multi_stop_plan_is_feasible():
    """The reported plan can actually be driven: fuel never runs out or overflows."""
    res = plan_refueling(
        total_distance_miles=1789.0,
        mpg=10.0,
        max_range_miles=500.0,
        candidates=[
            _station(429, 3.316),
            _station(823, 3.346),
            _station(1184, 3.017),
            _station(1543, 3.628),
            _station(1660, 3.048),
        ],
    )
    fuel = 50.0
    prev = 0.0
    for stop in res["fuel_stops"]:
        fuel -= (stop["route_mile"] - prev) / 10.0
        assert fuel >= -1e-6
        fuel += stop["gallons_filled"]
        assert fuel <= 50.0 + 1e-6
        prev = stop["route_mile"]
    # After the final stop, the remaining fuel must cover the leg to the destination.
    final_leg = (res["consumed_gallons"] * 10.0) - prev
    assert fuel - final_leg / 10.0 >= -1e-6



def test_unreachable_gap_raises():
    """A gap wider than the usable range with no station is infeasible."""
    with pytest.raises(ValueError, match="gap between refueling"):
        plan_refueling(
            total_distance_miles=1000.0,
            mpg=10.0,
            max_range_miles=500.0,
            candidates=[_station(100, 3.0)],
        )


@pytest.mark.parametrize("bad", [0, -5, float("nan"), float("inf"), None, "x"])
def test_invalid_inputs_rejected(bad):
    with pytest.raises(ValueError):
        plan_refueling(
            total_distance_miles=300.0,
            mpg=bad,
            max_range_miles=500.0,
            candidates=[],
        )


def test_matches_brute_force_on_random_cases():
    """The DP must match the exact brute-force optimum on randomized instances."""
    rng = random.Random(20261020)
    compared = 0
    for _ in range(25):
        total = round(rng.uniform(500.0, 2200.0), 1)
        miles = sorted(rng.sample(range(50, int(total) - 20), 5))
        stations = [_station(m, round(rng.uniform(2.9, 4.1), 3)) for m in miles]
        ref = _brute_force_cost(total, 10.0, 500.0, stations, 25.0)
        try:
            res = plan_refueling(total, 10.0, 500.0, stations)
        except ValueError:
            # Infeasible plans must agree with the reference.
            assert ref == float("inf"), f"DP said infeasible but brute={ref}"
            continue
        assert ref != float("inf"), "DP found a plan the reference deemed infeasible"
        compared += 1
        assert res["total_purchase_cost"] == pytest.approx(ref, abs=0.5), (
            f"DP {res['total_purchase_cost']} vs brute {ref} for {stations}"
        )
    assert compared > 0
