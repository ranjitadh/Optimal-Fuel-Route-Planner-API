from django.urls import path
from routing.views import (
    RouteOptimizationView,
    RouteMapView,
    FuelStopListView,
    HealthCheckView,
)

urlpatterns = [
    path("route/", RouteOptimizationView.as_view(), name="route-optimize"),
    path("route/map/", RouteMapView.as_view(), name="route-map"),
    path("fuel-stops/", FuelStopListView.as_view(), name="fuel-stops-list"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
