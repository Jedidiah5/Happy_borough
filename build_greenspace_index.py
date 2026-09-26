"""
Turns OS Open Greenspace site polygons into a compact per-borough JSON file
the app can load at startup, replacing the old 12-borough curated/estimated
green space benchmark with a real figure for all 33 London boroughs.

Source data: data/os_greenspace_borough_raw.csv
  -> OS Open Greenspace (GB-wide GeoPackage, Crown copyright, OS OpenData
     licence, https://www.ordnancesurvey.co.uk/products/os-open-greenspace),
     165,978 GB sites reduced to the 11,152 whose representative point falls
     inside a London borough. Each site's polygon area is summed per borough
     it was assigned to (by representative point, not a full boundary split,
     so a site straddling two boroughs is counted entirely in one of them --
     an acceptable approximation at borough scale). Borough land area comes
     from dissolving the same LSOA boundaries/LAD lookup
     build_lsoa_choropleth.py and build_deprivation_index.py already use, so
     the percentage is measured consistently with the rest of the app.
     Reproduced with shapely/pyproj in a one-off script (not part of this
     repo -- see the raw CSV's column comments below for what it computed).

Each borough gets its raw area figures plus a single 0-10 "green_space"
score: green_space_pct (greenspace area / borough land area) is min-max
normalized against the greenest/least green borough in the dataset, the same
approach build_rent_index.py uses for affordability.

Run:
    python build_greenspace_index.py

Output:
    data/greenspace_borough.json
"""
import csv
import json
import os

SRC_CSV = os.path.join(os.path.dirname(__file__), 'data', 'os_greenspace_borough_raw.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'greenspace_borough.json')


def build():
    boroughs = {}
    with open(SRC_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            land_area = float(row['land_area_sqm'])
            green_area = float(row['greenspace_area_sqm'])
            boroughs[row['borough']] = {
                'land_area_sqm': land_area,
                'greenspace_area_sqm': green_area,
                'site_count': int(row['site_count']),
                'green_space_pct': round(100 * green_area / land_area, 2),
            }

    pct_values = [b['green_space_pct'] for b in boroughs.values()]
    least_green, most_green = min(pct_values), max(pct_values)
    spread = (most_green - least_green) or 1.0

    for b in boroughs.values():
        # 10 = greenest borough in the dataset, 0 = least green.
        b['green_space_score'] = round(10 * (b['green_space_pct'] - least_green) / spread, 2)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(boroughs, f, indent=2, sort_keys=True)

    print(f"Wrote {len(boroughs)} London boroughs -> {OUT_JSON}")


if __name__ == '__main__':
    build()
