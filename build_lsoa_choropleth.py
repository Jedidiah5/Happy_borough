"""
Joins the LSOA boundary polygons + population-weighted centroids with the
English Indices of Deprivation 2025 LSOA-level data into a single compact
GeoJSON the app can serve straight to Leaflet for a neighborhood-level
choropleth -- the same 4,994 London LSOAs that build_deprivation_index.py
already aggregates up to borough level, but now at their native resolution.

Source data:
  data/lsoa_boundaries_london.geojson
    -> filtered from the ONS Open Geography Portal's "Lower Layer Super
       Output Areas (December 2021) Boundaries EW (BSC)" (generalised,
       clipped to coastline) down to London's 4,994 LSOAs.
  data/lsoa_pop_centroids_london.geojson
    -> filtered from the ONS "LSOA (Dec 2021) Population Weighted
       Centroids" down to the same 4,994 LSOAs.
  data/imd2025_london_lsoa.csv
    -> same IMD 2025 source build_deprivation_index.py uses.

Each output feature keeps its polygon geometry and gets a slim properties
object: LSOA code/name, borough, population-weighted centroid, and the same
8 IMD domains (score + decile) surfaced elsewhere in the app's API.

Run:
    python build_lsoa_choropleth.py

Output:
    data/lsoa_choropleth.json
"""
import csv
import json
import os

BOUNDARIES_PATH = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_boundaries_london.geojson')
CENTROIDS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_pop_centroids_london.geojson')
IMD_CSV_PATH = os.path.join(os.path.dirname(__file__), 'data', 'imd2025_london_lsoa.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_choropleth.json')

# Same domains/keys build_deprivation_index.py rolls up to borough level, so
# LSOA-level and borough-level figures line up in the API and the UI.
DOMAINS = [
    ("Index of Multiple Deprivation", "imd"),
    ("Income", "income"),
    ("Employment", "employment"),
    ("Education Skills and Training", "education"),
    ("Health Deprivation and Disability", "health"),
    ("Crime", "crime"),
    ("Barriers to Housing and Services", "housing_barriers"),
    ("Living Environment", "living_environment"),
]


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build():
    imd_by_lsoa = {}
    with open(IMD_CSV_PATH, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            imd_by_lsoa[row['LSOA code']] = row

    with open(CENTROIDS_PATH, encoding='utf-8') as f:
        centroids = json.load(f)
    centroid_by_lsoa = {
        f['properties']['LSOA21CD']: f['geometry']['coordinates']
        for f in centroids['features']
    }

    with open(BOUNDARIES_PATH, encoding='utf-8') as f:
        boundaries = json.load(f)

    out_features = []
    for feat in boundaries['features']:
        code = feat['properties']['LSOA21CD']
        imd_row = imd_by_lsoa.get(code)
        if not imd_row:
            continue

        domains = {}
        for prefix, key in DOMAINS:
            domains[key] = {
                'score': to_float(imd_row[f'{prefix} Score']),
                'decile': to_float(imd_row[f'{prefix} Decile']),
            }

        centroid = centroid_by_lsoa.get(code)

        out_features.append({
            'type': 'Feature',
            'geometry': feat['geometry'],
            'properties': {
                'lsoa_code': code,
                'lsoa_name': imd_row['LSOA name'],
                'borough': imd_row['Local Authority District name'],
                # GeoJSON point coordinates are [lng, lat]
                'centroid': centroid,
                'domains': domains,
            },
        })

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': out_features}, f)

    print(f"Wrote {len(out_features)} London LSOAs -> {OUT_JSON}")


if __name__ == '__main__':
    build()
