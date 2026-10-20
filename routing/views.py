import urllib.parse
from django.http import HttpResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from routing.models import FuelStop
from routing.serializers import (
    RouteRequestSerializer,
    RouteResponseSerializer,
    FuelStopModelSerializer,
    FuelStopRefuelSerializer,
)
from routing.services.geocoding import geocode_location
from routing.services.optimizer import optimize_fuel_route
from routing.services.map_service import generate_route_map_html

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500

class RouteOptimizationView(APIView):
    """
    POST /api/route/ or GET /api/route/
    Calculates driving route, cost-optimal fuel stops, and total fuel expenditure.
    """

    def get(self, request):
        serializer = RouteRequestSerializer(data=request.query_params)
        return self._process_request(request, serializer)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        return self._process_request(request, serializer)

    def _process_request(self, request, serializer):
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_query = serializer.validated_data["start"]
        finish_query = serializer.validated_data["finish"]
        max_range = serializer.validated_data.get("max_range", 500.0)
        mpg = serializer.validated_data.get("mpg", 10.0)

        # 1. Geocode locations
        try:
            start_info = geocode_location(start_query)
        except ValueError as e:
            return Response(
                {"error": "Invalid start location", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            finish_info = geocode_location(finish_query)
        except ValueError as e:
            return Response(
                {"error": "Invalid finish location", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_coords = (start_info["latitude"], start_info["longitude"])
        finish_coords = (finish_info["latitude"], finish_info["longitude"])

        # 2. Compute route and fuel stops
        try:
            optimization = optimize_fuel_route(
                start_coords=start_coords,
                finish_coords=finish_coords,
                max_range_miles=max_range,
                mpg=mpg,
            )
        except Exception as e:
            return Response(
                {"error": "Route optimization failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 3. Construct map URL
        map_url = (
            f"/api/route/map/?start={urllib.parse.quote(start_query)}&finish={urllib.parse.quote(finish_query)}"
        )
        if max_range != 500.0:
            map_url += f"&max_range={max_range}"
        if mpg != 10.0:
            map_url += f"&mpg={mpg}"

        response_data = {
            "start_location": {
                "query": start_query,
                "display_name": start_info["display_name"],
                "latitude": start_info["latitude"],
                "longitude": start_info["longitude"],
            },
            "finish_location": {
                "query": finish_query,
                "display_name": finish_info["display_name"],
                "latitude": finish_info["latitude"],
                "longitude": finish_info["longitude"],
            },
            "total_distance_miles": optimization["total_distance_miles"],
            "duration_hours": optimization["duration_hours"],
            "total_fuel_gallons": optimization["total_fuel_gallons"],
            "total_fuel_consumed_gallons": optimization["total_fuel_consumed_gallons"],
            "total_fuel_cost_usd": optimization["total_fuel_cost_usd"],
            "avg_price_per_gallon": optimization["avg_price_per_gallon"],
            "tank_capacity_gallons": optimization["tank_capacity_gallons"],
            "usable_range_miles": optimization["usable_range_miles"],
            "starting_fuel_gallons": optimization["starting_fuel_gallons"],
            "fuel_stops_count": optimization["fuel_stops_count"],
            "fuel_stops": optimization["fuel_stops"],
            "suggested_stop": optimization.get("suggested_stop"),
            "route_geometry": optimization["route_geometry"],
            "map_url": request.build_absolute_uri(map_url),
        }

        return Response(response_data, status=status.HTTP_200_OK)

class RouteMapView(APIView):
    """
    GET /api/route/map/
    Renders an interactive HTML map for direct visualization in browser.
    """

    def get(self, request):
        start_query = request.query_params.get("start")
        finish_query = request.query_params.get("finish")
        max_range = float(request.query_params.get("max_range", 500.0))
        mpg = float(request.query_params.get("mpg", 10.0))

        if not start_query or not finish_query:
            return HttpResponse(
                "<h3>Missing parameters: 'start' and 'finish' are required in query string.</h3>"
                "<p>Example: <code>/api/route/map/?start=New+York,+NY&finish=Los+Angeles,+CA</code></p>",
                status=400,
            )

        try:
            start_info = geocode_location(start_query)
            finish_info = geocode_location(finish_query)
            optimization = optimize_fuel_route(
                start_coords=(start_info["latitude"], start_info["longitude"]),
                finish_coords=(finish_info["latitude"], finish_info["longitude"]),
                max_range_miles=max_range,
                mpg=mpg,
            )
            html = generate_route_map_html(
                start_info,
                finish_info,
                optimization,
                max_range_miles=max_range,
                mpg=mpg,
            )
            return HttpResponse(html, content_type="text/html")
        except Exception as e:
            return HttpResponse(
                f"<h3>Error rendering route map</h3><p>{str(e)}</p>",
                status=500,
            )

class FuelStopListView(APIView):
    """
    GET /api/fuel-stops/
    Browse fuel stops database with filtering and pagination.
    """

    def get(self, request):
        queryset = FuelStop.objects.all()
        state = request.query_params.get("state")
        city = request.query_params.get("city")
        max_price = request.query_params.get("max_price")

        if state:
            queryset = queryset.filter(state__iexact=state.strip())
        if city:
            queryset = queryset.filter(city__icontains=city.strip())
        if max_price:
            try:
                queryset = queryset.filter(retail_price__lte=float(max_price))
            except ValueError:
                pass

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = FuelStopModelSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class HealthCheckView(APIView):
    """
    GET /api/health/
    Health and status check.
    """

    def get(self, request):
        return Response({
            "status": "healthy",
            "fuel_stops_count": FuelStop.objects.count(),
            "database_engine": request.COOKIES.get("db", "configured"),
        })
