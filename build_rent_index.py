"""
Turns the GLA "Housing in London 2025" report's borough rent table into a
compact per-borough JSON file the app can load at startup.

Source data: data/london_borough_rents_2025.csv
  -> transcribed from table 3.13 ("Average monthly private rent by number of
     bedrooms and London borough, September 2024 to August 2025") in
     "Housing in London 2025" (GLA), itself sourced from the ONS Price Index
     of Private Rents. Excludes any tenancy where the tenant receives Housing
     Benefit.

ONS doesn't publish this series for the City of London (population too small
for a reliable sample), so it's filled in with the London-wide average and
flagged `estimated`, matching how this app already handles the one borough
IMD 2025 or ONS well-being can't cover.

Each borough gets its four raw bedroom-count rents plus a single 0-10
"affordability" score: cheaper boroughs score higher, normalized against the
cheapest/most expensive borough in the dataset (using the average across all
four bedroom counts as the "typical rent" the score is based on).

Run:
    python build_rent_index.py

Output:
    data/rent_borough.json
"""
import csv
import json
import os

SRC_CSV = os.path.join(os.path.dirname(__file__), 'data', 'london_borough_rents_2025.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'rent_borough.json')

BEDROOM_COLS = ['rent_1bed', 'rent_2bed', 'rent_3bed', 'rent_4plusbed']

# The source table spells a handful of boroughs differently (& vs "and", or
# a shortened name) than the rest of this app's borough registry.
NAME_ALIASES = {
    'Barking & Dagenham': 'Barking and Dagenham',
    'Hammersmith & Fulham': 'Hammersmith and Fulham',
    'Kensington & Chelsea': 'Kensington and Chelsea',
    'Kingston': 'Kingston upon Thames',
    'Richmond': 'Richmond upon Thames',
}


def build():
    boroughs = {}
    with open(SRC_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = NAME_ALIASES.get(row['borough'], row['borough'])
            rents = {col: float(row[col]) for col in BEDROOM_COLS}
            boroughs[name] = {
                **rents,
                'typical_rent': round(sum(rents.values()) / len(rents), 2),
                'estimated': False,
            }

    typical_values = [b['typical_rent'] for b in boroughs.values()]
    london_avg = {
        col: round(sum(b[col] for b in boroughs.values()) / len(boroughs), 2)
        for col in BEDROOM_COLS
    }
    london_avg_typical = round(sum(typical_values) / len(typical_values), 2)

    # ONS doesn't publish a private-rent figure for the City of London; use
    # the London-wide average as a neutral stand-in, flagged as estimated.
    if 'City of London' not in boroughs:
        boroughs['City of London'] = {
            **london_avg,
            'typical_rent': london_avg_typical,
            'estimated': True,
        }
        typical_values.append(london_avg_typical)

    cheapest, priciest = min(typical_values), max(typical_values)
    spread = (priciest - cheapest) or 1.0

    for b in boroughs.values():
        # 10 = cheapest borough in the dataset, 0 = priciest.
        b['affordability_score'] = round(10 * (priciest - b['typical_rent']) / spread, 2)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(boroughs, f, indent=2, sort_keys=True)

    print(f"Wrote {len(boroughs)} London boroughs -> {OUT_JSON}")


if __name__ == '__main__':
    build()
