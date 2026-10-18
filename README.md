# Optimal Fuel Route Planner API (USA)

A production-ready **Django REST Framework (DRF)** backend API that computes driving routes between any two locations in the USA and determines the **cost-optimal fuel stops** along the route, strictly honoring vehicle range constraints (maximum **500 miles** per full tank) and computing total fuel expenditure based on **10 miles per gallon (10 MPG)**.

---

## 🌟 Key Features

- **Free Geospatial Routing & Geocoding**:
  - Routing engine via Open Source Routing Machine (**OSRM**): High-precision polyline, distance in meters, and driving time without requiring paid API keys.
  - Geocoding via OpenStreetMap **Nominatim**: Supports cities, states, addresses, or latitude/longitude coordinates with strict USA validation.
- **Cost-Optimal Fuel Optimizer**:
  - **100% US Fuel Stop Geocoding Coverage**: Preprocessed and mapped all **7,531** US truck stops from the provided OPIS dataset with latitude and longitude.
  - **Corridor Highway Search**: Evaluates stations within a 10-mile corridor along the route using Euclidean planar projection.
  - **500-Mile Tank Constraint**: Guarantees the vehicle never exceeds 500 miles between refuels.
  - **Greedy / Dynamic Cost Minimization**: Selects the most cost-effective stations in the reachable window to minimize total dollars spent.
- **Visual Map & Interactive Dashboard**:
  - **REST API**: Clean JSON responses with full route geometry (GeoJSON LineString), stop details, and cost metrics.
  - **Interactive Leaflet Map**: Rendered at `/api/route/map/` and integrated directly into the web dashboard at `/`.
- **Database Flexibility**:
  - Configured for **MySQL** (via `pymysql` and environment variables).
  - Built-in zero-configuration **SQLite** fallback for instant local testing.

---

## 📐 Mathematical Formulation

1. **Vehicle Constraints**:
   - $\text{Max Range} = 500 \text{ miles}$
   - $\text{Fuel Economy} = 10 \text{ MPG}$
   - $\text{Tank Capacity} = 500 / 10 = 50.0 \text{ gallons}$
2. **Total Fuel Consumed**:
   $$\text{Gallons Consumed} = \frac{\text{Total Distance (miles)}}{10.0}$$
3. **Refueling Optimization**:
   - For a route of distance $D$:
     - If $D \le 500 \text{ miles}$: The vehicle can complete the journey on one tank. The optimizer identifies the lowest-price station along the route to replenish fuel consumed at the cheapest rate.
     - If $D > 500 \text{ miles}$: The vehicle must refuel before running out of fuel. Refueling windows are evaluated ahead of current position ($d_{\text{curr}} \to d_{\text{curr}} + 475$ miles). The cheapest station in each reachable window is chosen, resetting range to 500 miles until destination is reached.
4. **Total Fuel Cost**:
   $$\text{Total Cost (USD)} = \sum_{k=1}^{N} \text{Gallons}_k \times \text{Price}_k$$

---

## 🚀 Quickstart & Installation

### 1. Prerequisites
- Python 3.10+ (or [uv](https://docs.astral.sh/uv/))

### 2. Setup Virtual Environment & Install Dependencies
```bash
# Clone / navigate to project
cd BE

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```
*(Or with `uv`: `uv pip install -r requirements.txt`)*

### 3. Run Migrations & Load Fuel Dataset
```bash
# Apply database migrations
python manage.py migrate

# Seed all 7,531 geocoded truckstops into the database
python manage.py load_fuel_prices
```

### 4. Start Development Server
```bash
python manage.py runserver 8000
```
Open **[http://localhost:8000/](http://localhost:8000/)** in your browser to view the interactive dashboard.

---

## 🗄️ MySQL Database Configuration

To connect the application to a **MySQL** database instance, set the following environment variables:

```bash
export DB_ENGINE="mysql"
export DB_NAME="fuel_routing_db"
export DB_USER="your_mysql_user"
export DB_PASSWORD="your_mysql_password"
export DB_HOST="127.0.0.1"
export DB_PORT="3306"

# Run migrations and load data into MySQL
python manage.py migrate
python manage.py load_fuel_prices
```

When `DB_ENGINE` is not set or set to `sqlite`, it automatically defaults to local `db.sqlite3`.

---

## 📡 API Endpoints

### 1. Route Optimization API
- **Endpoint**: `GET /api/route/` or `POST /api/route/`
- **Parameters**:
  - `start` (string, required): Origin in USA (e.g., `"New York, NY"`, address, or `"40.7128,-74.0060"`)
  - `finish` (string, required): Destination in USA (e.g., `"Los Angeles, CA"`)
  - `max_range` (float, optional, default: `500.0`): Max vehicle range in miles
  - `mpg` (float, optional, default: `10.0`): Fuel efficiency in miles per gallon

#### Example GET Request:
```bash
curl -X GET "http://localhost:8000/api/route/?start=New+York,+NY&finish=Chicago,+IL"
```

#### Example POST Request:
```bash
curl -X POST "http://localhost:8000/api/route/" \
  -H "Content-Type: application/json" \
  -d '{
    "start": "New York, NY",
    "finish": "Los Angeles, CA",
    "max_range": 500,
    "mpg": 10
  }'
```

#### Sample Response:
```json
{
  "start_location": {
    "query": "New York, NY",
    "display_name": "New York, United States",
    "latitude": 40.7127,
    "longitude": -74.0060
  },
  "finish_location": {
    "query": "Chicago, IL",
    "display_name": "Chicago, Illinois, United States",
    "latitude": 41.8781,
    "longitude": -87.6298
  },
  "total_distance_miles": 790.51,
  "duration_hours": 14.85,
  "total_fuel_gallons": 79.05,
  "total_fuel_cost_usd": 238.30,
  "fuel_stops_count": 2,
  "fuel_stops": [
    {
      "opis_id": 35,
      "truckstop_name": "ACI TRUCK STOP",
      "address": "ROUTE 80 & 94",
      "city": "Columbia",
      "state": "NJ",
      "retail_price": 3.079,
      "latitude": 40.9255,
      "longitude": -75.0934,
      "route_mile": 63.3,
      "leg_distance_miles": 63.3,
      "gallons_filled": 6.33,
      "cost_usd": 19.49
    },
    {
      "opis_id": 88,
      "truckstop_name": "S&G #88",
      "address": "I-80/90, EXIT 71",
      "city": "Toledo",
      "state": "OH",
      "retail_price": 3.009,
      "latitude": 41.6528,
      "longitude": -83.5379,
      "route_mile": 553.8,
      "leg_distance_miles": 490.5,
      "gallons_filled": 72.72,
      "cost_usd": 218.81
    }
  ],
  "route_geometry": {
    "type": "LineString",
    "coordinates": [[-74.0056, 40.7121], ...]
  },
  "map_url": "http://localhost:8000/api/route/map/?start=New+York%2C+NY&finish=Chicago%2C+IL"
}
```

---

### 2. Interactive Map Endpoint
- **Endpoint**: `GET /api/route/map/?start=...&finish=...`
- Returns a full standalone Leaflet map with colored route polyline, start/finish flags, and interactive fuel stop pins showing station names, addresses, price/gal, mile markers, and fuel cost.

---

### 3. Fuel Stops Database Query
- **Endpoint**: `GET /api/fuel-stops/`
- **Query Filters**: `state`, `city`, `max_price`, `page`
```bash
curl "http://localhost:8000/api/fuel-stops/?state=TX&max_price=3.10"
```

---

### 4. Health Check
- **Endpoint**: `GET /api/health/`
```bash
curl "http://localhost:8000/api/health/"
```

---

## 🧪 Running Automated Tests

Run the complete test suite with `pytest`:
```bash
pytest -v
```

The test suite validates:
- Geocoding and USA boundary enforcement
- Handling of coordinate inputs and invalid/international locations
- OSRM route calculations
- 500-mile vehicle range constraint guarantees (no leg exceeding 500 miles)
- Total fuel gallons and cost calculations
- All REST API endpoints and Leaflet HTML map rendering
