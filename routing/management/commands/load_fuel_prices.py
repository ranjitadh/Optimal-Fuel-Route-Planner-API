import csv
import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from routing.models import FuelStop

class Command(BaseCommand):
    help = "Loads geocoded fuel stops into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="data/fuel_prices_geocoded.csv",
            help="Path to the geocoded fuel prices CSV file",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing fuel stops before loading",
        )

    def handle(self, *args, **options):
        file_path = options.get("file")
        clear = options.get("clear", False)

        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        if clear or FuelStop.objects.exists():
            self.stdout.write("Clearing existing FuelStop records...")
            FuelStop.objects.all().delete()

        self.stdout.write(f"Reading from {file_path}...")
        fuel_stops = []
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rack_id = int(row["rack_id"]) if row.get("rack_id") and row["rack_id"].isdigit() else None
                    fuel_stops.append(
                        FuelStop(
                            opis_id=int(row["opis_id"]),
                            truckstop_name=row["truckstop_name"].strip(),
                            address=row["address"].strip(),
                            city=row["city"].strip(),
                            state=row["state"].strip(),
                            rack_id=rack_id,
                            retail_price=Decimal(str(row["retail_price"])),
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"]),
                        )
                    )
                except Exception as e:
                    continue

        self.stdout.write(f"Bulk inserting {len(fuel_stops)} fuel stops...")
        FuelStop.objects.bulk_create(fuel_stops, batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f"Successfully loaded {FuelStop.objects.count()} fuel stops!"))
