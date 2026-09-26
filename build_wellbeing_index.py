"""
Turns the official ONS Personal Well-being Survey time series (annual
population survey, local authority level) into a compact per-borough JSON
file the app can load at startup.

Source data: data/ons_wellbeing_london_boroughs.csv
  -> filtered from the official ONS release
     "wellbeing-local-authority-time-series-v4.csv" down to the 33 London
     boroughs (LAD codes starting E09) and the "average-mean" estimate type
     (there's also a "poor/fair/good/very-good" categorical breakdown in the
     source file, which this app doesn't use).

Each borough gets, for every survey year 2011-12 to 2022-23, a 0-10 mean
score (with published confidence interval) for all four ONS well-being
measures: Life satisfaction, Happiness, Worthwhile, and Anxiety (where a
*lower* anxiety score is better -- the other three are higher-is-better).

This replaces the old approach of hand-curating a single "happiness" figure
for 12 of 33 boroughs and falling back to a London-wide average (flagged
"estimated_benchmark") for the rest: every borough now gets a real, sourced
ONS figure, for every measure, every year.

Run:
    python build_wellbeing_index.py

Output:
    data/wellbeing_borough.json
"""
import csv
import json
import os

SRC_CSV = os.path.join(os.path.dirname(__file__), 'data', 'ons_wellbeing_london_boroughs.csv')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'data', 'wellbeing_borough.json')

# The measure that ships as this app's primary "happiness" slider value.
# ONS Life satisfaction is the most commonly cited headline well-being
# indicator, so it takes that role; the other three are kept alongside it
# for the borough detail popup.
HEADLINE_MEASURE = 'life-satisfaction'


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build():
    # borough -> measure -> year -> {mean, lower, upper}
    boroughs = {}

    with open(SRC_CSV, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            mean = to_float(row['mean_score'])
            if mean is None:
                # ONS suppresses the estimate for some (borough, year, measure)
                # combinations with too small a sample -- most notably the
                # City of London, which has no reliable figure for any
                # measure in any year (population ~8,000).
                continue
            b = boroughs.setdefault(row['borough'], {})
            m = b.setdefault(row['measure'], {})
            m[row['year']] = {
                'mean': mean,
                'lower': to_float(row['lower_limit']),
                'upper': to_float(row['upper_limit']),
            }

    def latest(series):
        """Most recent year with a real (non-suppressed) estimate, or (None, {})."""
        if not series:
            return None, {}
        year = max(series)
        return year, series[year]

    out = {}
    for name, measures in boroughs.items():
        headline_year, headline_latest = latest(measures.get(HEADLINE_MEASURE, {}))
        _, happiness_latest = latest(measures.get('happiness', {}))
        _, worthwhile_latest = latest(measures.get('worthwhile', {}))
        _, anxiety_latest = latest(measures.get('anxiety', {}))

        out[name] = {
            'latest_year': headline_year,
            'life_satisfaction': headline_latest.get('mean'),
            'life_satisfaction_range': [headline_latest.get('lower'), headline_latest.get('upper')],
            'happiness': happiness_latest.get('mean'),
            'worthwhile': worthwhile_latest.get('mean'),
            'anxiety': anxiety_latest.get('mean'),
            # Full time series per measure, for trend sparklines: [[year, mean], ...]
            'trend': {
                measure: sorted(
                    ([year, vals['mean']] for year, vals in series.items()),
                    key=lambda pair: pair[0],
                )
                for measure, series in measures.items()
            },
        }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print(f"Wrote {len(out)} London boroughs -> {OUT_JSON} ({len(out)} of 33 boroughs have at least one real estimate)")


if __name__ == '__main__':
    build()
