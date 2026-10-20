import pytest
from django.core.management import call_command
from routing.models import FuelStop

@pytest.fixture(autouse=True)
def seed_test_database(db):
    """Ensures test database has fuel stops loaded from pre-geocoded CSV."""
    if FuelStop.objects.count() == 0:
        call_command("load_fuel_prices", file="data/processed/fuel_prices_geocoded.csv")
