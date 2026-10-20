from rest_framework import serializers
from routing.models import FuelStop

class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        help_text="Start location (e.g. 'New York, NY', address, or '40.7128,-74.0060')",
    )
    finish = serializers.CharField(
        required=True,
        help_text="Finish location (e.g. 'Los Angeles, CA', address, or '34.0522,-118.2437')",
    )
    max_range = serializers.FloatField(
        required=False,
        default=500.0,
        min_value=50.0,
        help_text="Vehicle maximum range in miles on a full tank (default: 500.0)",
    )
    mpg = serializers.FloatField(
        required=False,
        default=10.0,
        min_value=1.0,
        help_text="Vehicle fuel economy in miles per gallon (default: 10.0)",
    )

class LocationInfoSerializer(serializers.Serializer):
    query = serializers.CharField()
    display_name = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

class FuelStopModelSerializer(serializers.ModelSerializer):
    """Serializer for FuelStop database records."""
    class Meta:
        model = FuelStop
        fields = [
            "id",
            "opis_id",
            "truckstop_name",
            "address",
            "city",
            "state",
            "rack_id",
            "retail_price",
            "latitude",
            "longitude",
        ]

class FuelStopRefuelSerializer(serializers.Serializer):
    """Serializer for fuel stops selected during route optimization."""
    opis_id = serializers.IntegerField(required=False, allow_null=True)
    truckstop_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    retail_price = serializers.FloatField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    route_mile = serializers.FloatField()
    leg_distance_miles = serializers.FloatField()
    gallons_filled = serializers.FloatField()
    cost_usd = serializers.FloatField()
    note = serializers.CharField(required=False, allow_null=True)

class SuggestedStopSerializer(serializers.Serializer):
    """Optional, unbilled refueling suggestion for trips covered by the start tank."""
    truckstop_name = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    retail_price = serializers.FloatField()
    route_mile = serializers.FloatField()

class RouteResponseSerializer(serializers.Serializer):
    start_location = LocationInfoSerializer()
    finish_location = LocationInfoSerializer()
    total_distance_miles = serializers.FloatField()
    duration_hours = serializers.FloatField()
    total_fuel_gallons = serializers.FloatField()
    total_fuel_consumed_gallons = serializers.FloatField()
    total_fuel_cost_usd = serializers.FloatField()
    avg_price_per_gallon = serializers.FloatField(allow_null=True)
    tank_capacity_gallons = serializers.FloatField()
    usable_range_miles = serializers.FloatField()
    starting_fuel_gallons = serializers.FloatField()
    fuel_stops_count = serializers.IntegerField()
    fuel_stops = FuelStopRefuelSerializer(many=True)
    suggested_stop = SuggestedStopSerializer(allow_null=True, required=False)
    route_geometry = serializers.DictField()
    map_url = serializers.CharField()
