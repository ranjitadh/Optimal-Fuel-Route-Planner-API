from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

from django.conf import settings

def home_view(request):
    carto_api_key = getattr(settings, 'CARTO_API_KEY', '') or getattr(settings, 'API_KEY', '')
    return render(request, "index.html", {"carto_api_key": carto_api_key})

urlpatterns = [
    path("", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]
