import io
import re
import zipfile
import pandas as pd
import requests

def generate_geocoded_dataset(
    source_path="data/raw/fuel-prices-for-be-assessment.csv",
    output_csv="data/processed/fuel_prices_geocoded.csv",
):
    print(f"Reading {source_path}...")
    df_fuel = pd.read_csv(source_path)

    def clean_str(s):
        if pd.isna(s):
            return ""
        return re.sub(r"[^A-Z0-9]", "", str(s).upper())

    df_fuel["city_key"] = df_fuel["City"].apply(clean_str)
    df_fuel["state_key"] = df_fuel["State"].apply(clean_str)

    print("Fetching GeoNames US dataset...")
    r = requests.get("https://download.geonames.org/export/zip/US.zip", timeout=30)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open("US.txt") as f:
        df_gn = pd.read_csv(
            f,
            sep="\t",
            header=None,
            usecols=[1, 2, 3, 4, 9, 10],
            names=["zip", "place_name", "admin_name1", "state_id", "lat", "lng"],
        )

    df_gn["city_key"] = df_gn["place_name"].apply(clean_str)
    df_gn["state_key"] = df_gn["state_id"].apply(clean_str)
    gn_map = df_gn.drop_duplicates(subset=["city_key", "state_key"])[
        ["city_key", "state_key", "lat", "lng"]
    ]

    print("Fetching SimpleMaps US Cities dataset...")
    cities_url = "https://simplemaps.com/static/data/us-cities/uscities.csv"
    df_sm = pd.read_csv(cities_url)
    df_sm["city_key"] = df_sm["city_ascii"].apply(clean_str)
    df_sm["state_key"] = df_sm["state_id"].apply(clean_str)
    sm_map = df_sm.drop_duplicates(subset=["city_key", "state_key"])[
        ["city_key", "state_key", "lat", "lng"]
    ]

    combined = pd.concat([gn_map, sm_map]).drop_duplicates(
        subset=["city_key", "state_key"]
    )

    extras = []
    for idx, row in combined.iterrows():
        c = row["city_key"]
        st = row["state_key"]
        lat = row["lat"]
        lng = row["lng"]
        if c.startswith("ST"):
            extras.append({"city_key": "SAINT" + c[2:], "state_key": st, "lat": lat, "lng": lng})
        if c.startswith("SAINT"):
            extras.append({"city_key": "ST" + c[5:], "state_key": st, "lat": lat, "lng": lng})
        if c.startswith("FT"):
            extras.append({"city_key": "FORT" + c[2:], "state_key": st, "lat": lat, "lng": lng})
        if c.startswith("FORT"):
            extras.append({"city_key": "FT" + c[4:], "state_key": st, "lat": lat, "lng": lng})

    if extras:
        combined = pd.concat([combined, pd.DataFrame(extras)]).drop_duplicates(
            subset=["city_key", "state_key"]
        )

    merged = pd.merge(df_fuel, combined, on=["city_key", "state_key"], how="left")

    us_states = set(df_sm["state_id"].unique())
    # Keep US stations
    us_matched = merged[merged["State"].isin(us_states) & merged["lat"].notnull()].copy()

    # Rename columns to standard clean names
    output_df = pd.DataFrame(
        {
            "opis_id": us_matched["OPIS Truckstop ID"],
            "truckstop_name": us_matched["Truckstop Name"].astype(str).str.strip(),
            "address": us_matched["Address"].astype(str).str.strip(),
            "city": us_matched["City"].astype(str).str.strip(),
            "state": us_matched["State"].astype(str).str.strip(),
            "rack_id": us_matched["Rack ID"],
            "retail_price": us_matched["Retail Price"].astype(float),
            "latitude": us_matched["lat"].astype(float),
            "longitude": us_matched["lng"].astype(float),
        }
    )

    output_df.to_csv(output_csv, index=False)
    print(f"Saved {len(output_df)} geocoded fuel stops to {output_csv}")

if __name__ == "__main__":
    import os
    os.makedirs("data/processed", exist_ok=True)
    generate_geocoded_dataset()
