"""
Aggregates the English Indices of Deprivation 2025 (IMD 2025) from LSOA level
(small areas, ~1,500 people) up to London borough level, and writes a compact
JSON file the app can load at startup.

Source data: data/imd2025_london_lsoa.csv
  -> filtered from the official MHCLG "IoD2025_Statistical_Release" file
     (2025_all_iod_scores_ranks_deciles.csv) down to the 33 London Local
     Authority Districts (LAD codes starting E09), 4,994 LSOAs.

Each LSOA's domain SCORE is combined into a borough figure using a
population-weighted mean (weight = Total population per LSOA), which is the
standard way to roll deprivation scores up from small areas to a larger area.
Deciles (1 = most deprived 10% in England, 10 = least deprived 10%) are
population-weighted-averaged too, giving an intuitive 1-10 "how deprived is
this borough relative to England" scale that lines up with the rest of the
app's 0-10 metrics (higher = better).

Run:
    python build_deprivation_index.py

Output:
    data/deprivation_borough.json
"""
import csv
import json
import os

SRC_CSV = os.path.join(os.path.dirname(__file__), 'data', 'imd2025_london_lsoa.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'deprivation_borough.json')

# (csv column prefix, output key) -- each domain has a "<prefix> Score" and
# "<prefix> Decile" column in the source file.
DOMAINS = [
    ("Index of Multiple Deprivation", "imd"),
    ("Income", "income"),
    ("Employment", "employment"),
    ("Education Skills and Training", "education"),
    ("Health Deprivation and Disability", "health"),
    ("Crime", "crime"),
    ("Barriers to Housing and Services", "housing_barriers"),
    ("Living Environment", "living_environment"),
    ("IDACI", "child_poverty"),
    ("IDAOPI", "older_person_poverty"),
]

POP_COLS = {
    "population": "Total population",
    "dependent_children": "Dependent Children",
    "older_population": "Older population",
    "working_age_population": "Working age population",
}


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build():
    boroughs = {}  # code -> accumulator dict

    with open(SRC_CSV, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row['Local Authority District code']
            name = row['Local Authority District name']
            pop = to_float(row[POP_COLS['population']]) or 1.0  # avoid zero weight

            b = boroughs.setdefault(code, {
                'borough': name,
                'lsoa_count': 0,
                'weight_sum': 0.0,
                'population': 0.0,
                'dependent_children': 0.0,
                'older_population': 0.0,
                'working_age_population': 0.0,
                'domain_score_sum': {key: 0.0 for _, key in DOMAINS},
                'domain_decile_sum': {key: 0.0 for _, key in DOMAINS},
            })

            b['lsoa_count'] += 1
            b['weight_sum'] += pop
            for pop_key, csv_col in POP_COLS.items():
                b[pop_key] += to_float(row[csv_col])

            for prefix, key in DOMAINS:
                score = to_float(row[f'{prefix} Score'])
                decile = to_float(row[f'{prefix} Decile'])
                b['domain_score_sum'][key] += score * pop
                b['domain_decile_sum'][key] += decile * pop

    out = {}
    for code, b in boroughs.items():
        w = b['weight_sum']
        entry = {
            'borough': b['borough'],
            'lad_code': code,
            'lsoa_count': b['lsoa_count'],
            'population': int(round(b['population'])),
            'dependent_children': int(round(b['dependent_children'])),
            'older_population': int(round(b['older_population'])),
            'working_age_population': int(round(b['working_age_population'])),
            'domains': {},
        }
        for _, key in DOMAINS:
            entry['domains'][key] = {
                'score': round(b['domain_score_sum'][key] / w, 3),
                'decile': round(b['domain_decile_sum'][key] / w, 2),
            }
        out[b['borough']] = entry

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print(f"Wrote {len(out)} London boroughs -> {OUT_JSON}")


if __name__ == '__main__':
    build()
