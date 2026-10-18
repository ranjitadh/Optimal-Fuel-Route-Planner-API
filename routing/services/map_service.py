import folium
from folium import plugins

def generate_route_map_html(
    start_info: dict,
    finish_info: dict,
    optimization_result: dict,
) -> str:
    """
    Renders an interactive Leaflet HTML map with route polyline,
    start/finish markers, and optimal fuel stop pins.
    """
    coords = optimization_result["route_geometry"]["coordinates"]  # [[lon, lat], ...]
    # Folium expects [lat, lon]
    route_latlons = [[c[1], c[0]] for c in coords]

    # Map center and bounds
    all_lats = [c[1] for c in coords]
    all_lons = [c[0] for c in coords]
    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Draw Route Polyline
    folium.PolyLine(
        locations=route_latlons,
        color="#2563EB",  # Vibrant royal blue
        weight=5,
        opacity=0.85,
        tooltip=f"Route: {optimization_result['total_distance_miles']} miles",
    ).add_to(m)

    # Start Marker (Green)
    start_lat = start_info["latitude"]
    start_lon = start_info["longitude"]
    folium.Marker(
        location=[start_lat, start_lon],
        popup=folium.Popup(
            f"""
            <div style="font-family: sans-serif; min-width: 180px;">
                <h4 style="margin: 0 0 6px 0; color: #16a34a;">🏁 Start Location</h4>
                <p style="margin: 0; font-size: 13px;"><b>{start_info.get('display_name', 'Start')}</b></p>
                <p style="margin: 4px 0 0 0; color: #64748b; font-size: 12px;">Mile 0.0</p>
            </div>
            """,
            max_width=300,
        ),
        tooltip="Start Location",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)

    # Finish Marker (Red)
    finish_lat = finish_info["latitude"]
    finish_lon = finish_info["longitude"]
    folium.Marker(
        location=[finish_lat, finish_lon],
        popup=folium.Popup(
            f"""
            <div style="font-family: sans-serif; min-width: 180px;">
                <h4 style="margin: 0 0 6px 0; color: #dc2626;">🎯 Destination</h4>
                <p style="margin: 0; font-size: 13px;"><b>{finish_info.get('display_name', 'Finish')}</b></p>
                <p style="margin: 4px 0 0 0; color: #64748b; font-size: 12px;">Mile {optimization_result['total_distance_miles']}</p>
            </div>
            """,
            max_width=300,
        ),
        tooltip="Destination",
        icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa"),
    ).add_to(m)

    # Fuel Stops Markers (Orange)
    fuel_stops = optimization_result.get("fuel_stops", [])
    for idx, stop in enumerate(fuel_stops, start=1):
        stop_lat = stop["latitude"]
        stop_lon = stop["longitude"]
        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 220px; padding: 4px;">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="background: #ea580c; color: white; border-radius: 50%; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; margin-right: 6px;">{idx}</span>
                <b style="font-size: 14px; color: #0f172a;">{stop['truckstop_name']}</b>
            </div>
            <div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
                📍 {stop['address']}, {stop['city']}, {stop['state']}
            </div>
            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 6px 0;" />
            <table style="width: 100%; font-size: 12px;">
                <tr><td style="color: #64748b;">Fuel Price:</td><td style="font-weight: bold; color: #16a34a; text-align: right;">${stop['retail_price']:.3f} / gal</td></tr>
                <tr><td style="color: #64748b;">Route Mile:</td><td style="text-align: right;">Mile {stop['route_mile']}</td></tr>
                <tr><td style="color: #64748b;">Gallons Filled:</td><td style="text-align: right;">{stop['gallons_filled']} gal</td></tr>
                <tr><td style="color: #64748b;">Cost:</td><td style="font-weight: bold; text-align: right; color: #0284c7;">${stop['cost_usd']:.2f}</td></tr>
            </table>
        </div>
        """
        folium.Marker(
            location=[stop_lat, stop_lon],
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"Fuel Stop #{idx}: {stop['truckstop_name']} (${stop['retail_price']}/gal)",
            icon=folium.Icon(color="orange", icon="gas-pump", prefix="fa"),
        ).add_to(m)

    # Fit bounds
    m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])

    # Top summary card injection
    card_html = f"""
    <div style="
        position: fixed;
        top: 15px;
        left: 55px;
        z-index: 1000;
        background: rgba(15, 23, 42, 0.92);
        backdrop-filter: blur(8px);
        color: white;
        padding: 14px 20px;
        border-radius: 12px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        border: 1px solid rgba(255, 255, 255, 0.1);
        max-width: 420px;
    ">
        <h3 style="margin: 0 0 8px 0; font-size: 16px; font-weight: 700; color: #38bdf8;">Optimal Fuel Route Planner</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px;">
            <div><span style="color: #94a3b8;">Total Distance:</span><br/><b style="font-size: 15px;">{optimization_result['total_distance_miles']} mi</b></div>
            <div><span style="color: #94a3b8;">Total Fuel Cost:</span><br/><b style="font-size: 15px; color: #4ade80;">${optimization_result['total_fuel_cost_usd']}</b></div>
            <div><span style="color: #94a3b8;">Fuel Consumed:</span><br/><b>{optimization_result['total_fuel_gallons']} gal</b> (10 mpg)</div>
            <div><span style="color: #94a3b8;">Optimal Stops:</span><br/><b>{optimization_result['fuel_stops_count']} stops</b> (max 500 mi range)</div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(card_html))

    return m.get_root().render()
