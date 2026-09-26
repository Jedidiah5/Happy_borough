"""
Builds a real, per-borough Transport Accessibility score from TfL's Public
Transport Accessibility Level (PTAL) data, aggregated to ward level.

Replaces the old approach for transport, which was a hand-typed 0-10 guess
for 12 of 33 boroughs and a plain average of those 12 for the rest (see
BOROUGH_HAPPINESS_DATA in happiness_server.py) -- unlike every other metric
in this app, transport never had a real, sourced dataset behind it, despite
being labelled "TfL PTAL" in the README.

Source data:
  data/tfl_ward_ptal_2023.geojson
    -> 704 London wards (December 2024 boundaries, WD24CD), each carrying
       MEAN_AI / MEDIAN_AI / MIN_AI / MAX_AI (TfL's Accessibility Index,
       continuous and unbounded upward) and MEAN_PTAL_ (the official PTAL
       band: 1a, 1b, 2, 3, 4, 5, 6a, 6b -- 1a worst, 6b best). Field names
       (FID, GlobalID, Shape__Area, MEAN_AI/MEDIAN_AI) match an Esri
       "Summarize Within" aggregation of TfL's PTAL point/grid data onto
       the ward boundaries -- supplied directly rather than fetched from a
       specific TfL/GLA download page, so treat the exact publishing URL as
       unconfirmed even though the methodology and values are TfL's own.
  data/lsoa_pop_centroids_london.geojson
    -> ONS population-weighted centroids for London's 4,994 LSOAs (already
       in the repo; same file build_lsoa_choropleth.py uses).
  data/imd2025_london_lsoa.csv
    -> same IMD 2025 source build_deprivation_index.py uses, for each
       LSOA's borough name and population.

Method: the ward layer has no borough field, so each LSOA's population-
weighted centroid is spatially joined to whichever ward polygon contains it,
picking up that ward's PTAL stats. LSOAs are then rolled up to their borough
using the same population-weighted mean as build_deprivation_index.py, so a
borough with more people living in well-connected wards counts for more than
one with more people in poorly-connected wards -- not a flat average of
however many wards happen to fall in the borough.

The population-weighted mean Accessibility Index is then rescaled 0-10 using
min-max, the same convention build_rent_index.py uses for affordability --
but City of London is excluded from the min/max range itself. Its ~8,000
residents share the Square Mile with the densest transport interchange in
the country (its Accessibility Index, ~81, is more than double the next
borough's), so including it would compress the other 32 boroughs' genuine
spread into a sliver of the 0-10 scale, even though it's the "boroughs
where people actually live and commute" spread that this app's composite
score cares about. City of London itself is clamped to 10 -- it is, after
all, still the most accessible point in London by a wide margin.

Run:
    python build_transport_index.py

Output:
    data/transport_borough.json
"""
import csv
import json
import os

import geopandas as gpd
from shapely.geometry import shape

WARD_PTAL_PATH = os.path.join(os.path.dirname(__file__), 'data', 'tfl_ward_ptal_2023.geojson')
LSOA_CENTROIDS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_pop_centroids_london.geojson')
IMD_CSV_PATH = os.path.join(os.path.dirname(__file__), 'data', 'imd2025_london_lsoa.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'transport_borough.json')

# Ordinal position of each PTAL band, worst to best. Only used to compute a
# population-weighted "typical band" per borough for display -- the actual
# transport score is derived from the continuous Accessibility Index instead,
# since collapsing to 8 bands loses most of the signal.
PTAL_BAND_ORDER = ['0', '1a', '1b', '2', '3', '4', '5', '6a', '6b']


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build():
    wards = gpd.read_file(WARD_PTAL_PATH)[['WD24CD', 'MEAN_AI', 'MEAN_PTAL_', 'geometry']]
    if wards.crs is None:
        wards = wards.set_crs('EPSG:4326')

    with open(LSOA_CENTROIDS_PATH, encoding='utf-8') as f:
        centroids_geojson = json.load(f)
    lsoa_points = gpd.GeoDataFrame(
        [{'LSOA21CD': feat['properties']['LSOA21CD']} for feat in centroids_geojson['features']],
        geometry=[shape(feat['geometry']) for feat in centroids_geojson['features']],
        crs='EPSG:4326',
    )

    joined = gpd.sjoin(lsoa_points, wards.to_crs(lsoa_points.crs), how='left', predicate='within')
    joined = joined[~joined.index.duplicated(keep='first')]  # a centroid exactly on a shared edge can match 2 wards

    # A handful of population-weighted centroids can land just outside every
    # ward polygon (simplified/generalised boundaries, coastline clipping):
    # snap those to the nearest ward instead of dropping the LSOA.
    unmatched = joined[joined['WD24CD'].isna()].index
    if len(unmatched):
        nearest = gpd.sjoin_nearest(lsoa_points.loc[unmatched], wards.to_crs(lsoa_points.crs))
        nearest = nearest[~nearest.index.duplicated(keep='first')]
        for col in ['WD24CD', 'MEAN_AI', 'MEAN_PTAL_']:
            joined.loc[unmatched, col] = nearest[col]

    lsoa_to_ward = dict(zip(joined['LSOA21CD'], zip(joined['MEAN_AI'], joined['MEAN_PTAL_'])))

    imd_by_lsoa = {}
    with open(IMD_CSV_PATH, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            imd_by_lsoa[row['LSOA code']] = {
                'borough': row['Local Authority District name'],
                'population': to_float(row['Total population']) or 1.0,
            }

    boroughs = {}  # name -> accumulator
    unresolved = 0
    for lsoa_code, (ai, band) in lsoa_to_ward.items():
        info = imd_by_lsoa.get(lsoa_code)
        if not info or ai is None:
            unresolved += 1
            continue
        b = boroughs.setdefault(info['borough'], {'weight_sum': 0.0, 'ai_sum': 0.0, 'band_sum': 0.0, 'lsoa_count': 0})
        pop = info['population']
        b['weight_sum'] += pop
        b['ai_sum'] += ai * pop
        band_idx = PTAL_BAND_ORDER.index(band) if band in PTAL_BAND_ORDER else None
        if band_idx is not None:
            b['band_sum'] += band_idx * pop
        b['lsoa_count'] += 1

    borough_ai = {name: b['ai_sum'] / b['weight_sum'] for name, b in boroughs.items()}
    # City of London's Accessibility Index is so far above every other
    # borough's that including it in the min/max range would flatten the
    # other 32 boroughs' real spread into a sliver of the scale (see the
    # module docstring) -- exclude it from the range, then clamp its own
    # score at 10.
    OUTLIER = 'City of London'
    scale_values = [ai for name, ai in borough_ai.items() if name != OUTLIER]
    worst, best = min(scale_values), max(scale_values)
    spread = (best - worst) or 1.0

    out = {}
    for name, b in boroughs.items():
        mean_ai = borough_ai[name]
        band_idx = round(b['band_sum'] / b['weight_sum'])
        transport_score = 10.0 if name == OUTLIER else 10 * (mean_ai - worst) / spread
        out[name] = {
            'mean_accessibility_index': round(mean_ai, 2),
            'ptal_band': PTAL_BAND_ORDER[band_idx],
            'transport_score': round(min(10.0, max(0.0, transport_score)), 2),
            'lsoa_count': b['lsoa_count'],
        }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print(f"Wrote {len(out)} London boroughs -> {OUT_JSON} ({unresolved} LSOAs unresolved)")


if __name__ == '__main__':
    build()
