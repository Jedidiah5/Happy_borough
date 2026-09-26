import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import sqlite3
import os
import sys
import time
import threading
import concurrent.futures

# Some Windows terminals default stdout to a legacy codepage (cp1252) that
# can't encode the emoji in this file's log messages; force UTF-8 so the
# server doesn't crash on startup in those environments.
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PORT = int(os.environ.get('PORT', 8085))
DB_PATH = 'housing.db'
DEPRIVATION_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'deprivation_borough.json')
WELLBEING_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'wellbeing_borough.json')
RENT_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'rent_borough.json')
LSOA_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_choropleth.json')

# Baseline Police Stats + TfL PTAL benchmarks. Only available for a subset of
# boroughs (the ones with a hand-curated published figure) -- every other
# borough is filled in from a London-wide average (see LONDON_AVERAGE),
# flagged in the API response so the UI can be honest about it. (Real,
# per-borough ONS well-being data for 32 of 33 boroughs comes from
# WELLBEING_DATA below instead of this dict -- see build_wellbeing_index.py.)
BOROUGH_HAPPINESS_DATA = {
    "Richmond upon Thames": {"safety": 8.8, "green_space": 9.4, "transport": 6.8, "lat": 51.4479, "lng": -0.3260},
    "Wandsworth":           {"safety": 7.8, "green_space": 8.5, "transport": 9.1, "lat": 51.4567, "lng": -0.1910},
    "Kingston upon Thames": {"safety": 8.6, "green_space": 8.9, "transport": 7.0, "lat": 51.4085, "lng": -0.3064},
    "Kensington and Chelsea":{"safety": 6.5, "green_space": 8.0, "transport": 9.5, "lat": 51.5020, "lng": -0.1947},
    "Barnet":               {"safety": 8.0, "green_space": 8.8, "transport": 7.5, "lat": 51.6252, "lng": -0.2000},
    "Camden":               {"safety": 5.8, "green_space": 8.3, "transport": 9.8, "lat": 51.5290, "lng": -0.1255},
    "Ealing":               {"safety": 7.2, "green_space": 7.9, "transport": 8.2, "lat": 51.5130, "lng": -0.3089},
    "Bromley":              {"safety": 8.4, "green_space": 9.2, "transport": 6.5, "lat": 51.4039, "lng": 0.0198},
    "Hackney":              {"safety": 5.5, "green_space": 7.6, "transport": 9.2, "lat": 51.5450, "lng": -0.0553},
    "Croydon":              {"safety": 6.8, "green_space": 8.1, "transport": 7.8, "lat": 51.3762, "lng": -0.0982},
    "Brent":                {"safety": 6.2, "green_space": 7.2, "transport": 8.0, "lat": 51.5588, "lng": -0.2817},
    "Greenwich":            {"safety": 7.5, "green_space": 8.6, "transport": 7.9, "lat": 51.4892, "lng": 0.0053}
}

# Borough centroid coordinates for every London borough not already listed
# above, so the remaining 21 boroughs can be plotted on the map and queried
# against the live UK Police API. (Approximate geographic centroids.)
EXTRA_BOROUGH_COORDS = {
    "Barking and Dagenham":   {"lat": 51.5540, "lng": 0.1500},
    "Bexley":                 {"lat": 51.4549, "lng": 0.1505},
    "City of London":         {"lat": 51.5155, "lng": -0.0922},
    "Enfield":                {"lat": 51.6538, "lng": -0.0799},
    "Hammersmith and Fulham": {"lat": 51.4927, "lng": -0.2339},
    "Haringey":               {"lat": 51.6000, "lng": -0.1119},
    "Harrow":                 {"lat": 51.5898, "lng": -0.3346},
    "Havering":               {"lat": 51.5779, "lng": 0.1830},
    "Hillingdon":             {"lat": 51.5441, "lng": -0.4760},
    "Hounslow":               {"lat": 51.4746, "lng": -0.3680},
    "Islington":              {"lat": 51.5416, "lng": -0.1022},
    "Lambeth":                {"lat": 51.4607, "lng": -0.1163},
    "Lewisham":               {"lat": 51.4452, "lng": -0.0209},
    "Merton":                 {"lat": 51.4098, "lng": -0.1949},
    "Newham":                 {"lat": 51.5077, "lng": 0.0469},
    "Redbridge":              {"lat": 51.5590, "lng": 0.0741},
    "Southwark":              {"lat": 51.4730, "lng": -0.0800},
    "Sutton":                 {"lat": 51.3618, "lng": -0.1945},
    "Tower Hamlets":          {"lat": 51.5150, "lng": -0.0172},
    "Waltham Forest":         {"lat": 51.5908, "lng": -0.0134},
    "Westminster":            {"lat": 51.4973, "lng": -0.1372},
}


def load_json_data(path, label):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Could not load {label} ({path}): {e}")
        return {}


DEPRIVATION_DATA = load_json_data(DEPRIVATION_JSON_PATH, "IMD 2025 deprivation data")

# Real ONS Personal Well-being Survey figures for 32 of 33 boroughs, every
# survey year 2011-12 to 2022-23, built by build_wellbeing_index.py from
# data/ons_wellbeing_london_boroughs.csv. Replaces the old 12-borough
# curated/estimated split for happiness -- every borough but the City of
# London (population too small for ONS to publish a figure) has a genuine,
# sourced figure here.
WELLBEING_DATA = load_json_data(WELLBEING_JSON_PATH, "ONS well-being data")

# Real GLA/ONS private rent figures for 32 of 33 boroughs (City of London is
# too small for ONS to publish a figure, so it gets a flagged London-wide
# average instead), built by build_rent_index.py from
# data/london_borough_rents_2025.csv.
RENT_DATA = load_json_data(RENT_JSON_PATH, "borough rent data")

# LSOA-level (neighborhood, ~1,500 people) IMD 2025 choropleth geometry for
# all 4,994 London small areas, built by build_lsoa_choropleth.py. Read once
# as raw bytes at startup and served as-is by /api/lsoa-geo -- it's just a
# static GeoJSON payload for Leaflet, so there's no need to re-parse/dump it
# on every request.
try:
    with open(LSOA_GEOJSON_PATH, 'rb') as f:
        LSOA_GEOJSON_BYTES = f.read()
except Exception as e:
    print(f"⚠️ Could not load LSOA choropleth geometry ({LSOA_GEOJSON_PATH}): {e}")
    LSOA_GEOJSON_BYTES = b'{"type":"FeatureCollection","features":[]}'

# London-wide average of the TfL/green-space benchmarks and of the ONS
# well-being measures, used as a neutral stand-in for boroughs that don't
# have their own figure (flagged as "estimated" in the API response so the
# UI can be honest about it). The City of London's population (~8,000) is
# too small for ONS to publish a reliable well-being estimate for any
# measure, so it's the one borough that needs this fallback for happiness.
LONDON_AVERAGE = {
    "green_space": round(sum(d["green_space"] for d in BOROUGH_HAPPINESS_DATA.values()) / len(BOROUGH_HAPPINESS_DATA), 2),
    "transport": round(sum(d["transport"] for d in BOROUGH_HAPPINESS_DATA.values()) / len(BOROUGH_HAPPINESS_DATA), 2),
    "wellbeing": {
        measure: round(sum(v for v in values if v is not None) / len([v for v in values if v is not None]), 2)
        for measure in ("life_satisfaction", "happiness", "worthwhile", "anxiety")
        for values in [[b.get(measure) for b in WELLBEING_DATA.values()]]
    },
}


def build_borough_registry():
    """
    Full 33-borough registry: starts from IMD 2025 coverage (all London
    boroughs) and layers the curated TfL/green-space benchmarks, real ONS
    well-being data, and real rent/affordability data on top -- falling back
    to a flagged London-wide average for the handful of fields (green space,
    transport, and the City of London's well-being/rent) that don't have a
    full 33-borough open data source.
    """
    registry = {}
    for name, dep in DEPRIVATION_DATA.items():
        coords = BOROUGH_HAPPINESS_DATA.get(name) or EXTRA_BOROUGH_COORDS.get(name)
        if not coords:
            continue
        curated = BOROUGH_HAPPINESS_DATA.get(name)
        crime_decile = dep["domains"]["crime"]["decile"]
        wellbeing = WELLBEING_DATA.get(name)
        wellbeing_estimated = wellbeing is None
        if wellbeing is None:
            wellbeing = {**LONDON_AVERAGE["wellbeing"], "latest_year": None, "life_satisfaction_range": [None, None], "trend": {}}
        rent = RENT_DATA.get(name, {})
        registry[name] = {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "happiness": wellbeing.get("life_satisfaction"),
            "wellbeing": wellbeing,
            "wellbeing_estimated": wellbeing_estimated,
            "green_space": curated["green_space"] if curated else LONDON_AVERAGE["green_space"],
            "transport": curated["transport"] if curated else LONDON_AVERAGE["transport"],
            # Fallback used only if the live Police API call fails: prefer
            # the curated benchmark, otherwise derive one from IMD's Crime
            # domain decile (already on a comparable 1-10, higher-is-safer scale).
            "safety": curated["safety"] if curated else round(crime_decile, 1),
            "estimated_green_transport": curated is None,
            "rent": rent,
            "affordability": rent.get("affordability_score", 5.0),
            "deprivation": dep,
        }
    return registry


BOROUGH_REGISTRY = build_borough_registry()

# In-memory thread-safe cache for UK Police API calls
# Structure: {borough_name: (safety_score, raw_crime_count, timestamp, is_live)}
POLICE_SAFETY_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache to prevent rate-limiting

def fetch_police_safety(borough_name, lat, lng, fallback_score):
    """
    Query the official UK Police API (data.police.uk) for live street-level crime records.
    If the request fails, times out, is rate-limited, or crashes, it automatically
    reverts to the previous benchmark version (fallback_score).
    """
    now = time.time()
    if borough_name in POLICE_SAFETY_CACHE:
        cached_score, cached_count, cached_time, is_live = POLICE_SAFETY_CACHE[borough_name]
        if now - cached_time < CACHE_TTL:
            return cached_score, cached_count, is_live

    url = f"https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lng}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'HappyBorough-London-App/1.0'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            if resp.status == 200:
                crimes = json.loads(resp.read().decode('utf-8'))
                if isinstance(crimes, list):
                    count = len(crimes)
                    # Convert crime volume to 0-10 safety rating (fewer crimes = higher score)
                    score = round(max(4.0, min(9.6, 9.8 - (count / 650.0))), 1)
                    POLICE_SAFETY_CACHE[borough_name] = (score, count, now, True)
                    return score, count, True
    except Exception as e:
        # Revert to previous benchmark version on any error
        print(f"⚠️ UK Police API note for {borough_name}: {e}. Reverting to previous benchmark ({fallback_score}).")

    POLICE_SAFETY_CACHE[borough_name] = (fallback_score, None, now, False)
    return fallback_score, None, False

def warm_police_cache_async():
    """Warm the cache in the background so initial slider movements are instant."""
    def _worker():
        for b_name, data in BOROUGH_REGISTRY.items():
            try:
                fetch_police_safety(b_name, data['lat'], data['lng'], data['safety'])
                time.sleep(0.25)  # Gentle spacing to respect police API guidelines
            except Exception:
                pass
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

# housing.db's area_name column uses shortened names for a handful of
# boroughs (confirmed via `SELECT DISTINCT area_name`), which never match a
# `LIKE '%<full borough name>%'` query in the other direction.
HOUSING_DB_AREA_NAME_ALIASES = {
    "Richmond upon Thames": "Richmond",
    "Kingston upon Thames": "Kingston",
    "Kensington and Chelsea": "Kensington",
    "City of London": "City",
}


def get_housing_metrics(borough_name):
    if not os.path.exists(DB_PATH):
        return {"total_apps": 5000, "approval_rate": 80.0}
    query_name = HOUSING_DB_AREA_NAME_ALIASES.get(borough_name, borough_name)
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status IN ('Permitted', 'Conditions') THEN 1 ELSE 0 END) as permitted
            FROM applications
            WHERE LOWER(area_name) LIKE LOWER(?)
        ''', (f"%{query_name}%",))
        row = c.fetchone()
        conn.close()
        if row and row[0] > 0:
            return {
                "total_apps": row[0],
                "approval_rate": round((row[1] / row[0]) * 100, 1)
            }
    except Exception as e:
        print(f"Housing metrics query note: {e}")
    return {"total_apps": 0, "approval_rate": 75.0}

class HappinessHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/api/rankings':
            params = urllib.parse.parse_qs(parsed.query)
            w_safety = float(params.get('w_safety', [0.20])[0])
            w_green = float(params.get('w_green', [0.20])[0])
            w_transport = float(params.get('w_transport', [0.15])[0])
            w_happiness = float(params.get('w_happiness', [0.15])[0])
            w_barriers = float(params.get('w_barriers', [0.15])[0])
            w_affordability = float(params.get('w_affordability', [0.15])[0])

            # Fetch safety for all boroughs concurrently -- doing this one
            # borough at a time (up to a 3.5s timeout each) made a cold-cache
            # request take 30+ seconds, long enough that the browser gave up
            # and aborted the connection before the response was ready.
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                safety_results = dict(pool.map(
                    lambda item: (item[0], fetch_police_safety(item[0], item[1]['lat'], item[1]['lng'], item[1]['safety'])),
                    BOROUGH_REGISTRY.items(),
                ))

            rankings = []
            for b_name, data in BOROUGH_REGISTRY.items():
                housing = get_housing_metrics(b_name)
                dep = data['deprivation']['domains']
                wellbeing = data['wellbeing']
                rent = data['rent']
                safety_score, crime_count, is_live = safety_results[b_name]

                # IMD 2025 "Barriers to Housing and Services" decile: higher =
                # fewer barriers (better affordability/access), same
                # higher-is-better direction as every other 0-10 metric here.
                barriers_decile = dep['housing_barriers']['decile']

                # Weighted Happiness Score (scaled to 100)
                score = (
                    (safety_score * 10 * w_safety) +
                    (data['green_space'] * 10 * w_green) +
                    (data['transport'] * 10 * w_transport) +
                    (data['happiness'] * 10 * w_happiness) +
                    (barriers_decile * 10 * w_barriers) +
                    (data['affordability'] * 10 * w_affordability)
                )

                rankings.append({
                    "borough": b_name,
                    "overall_score": round(score, 1),
                    "ons_happiness": data['happiness'],
                    "estimated_benchmark": data['estimated_green_transport'],
                    "safety_score": safety_score,
                    "safety_source": "live_api" if is_live else "benchmark_fallback",
                    "recent_crimes": crime_count,
                    "green_space": data['green_space'],
                    "transport_score": data['transport'],
                    "housing_apps": housing['total_apps'],
                    "housing_approval_rate": housing['approval_rate'],
                    "lat": data['lat'],
                    "lng": data['lng'],
                    # Official ONS Personal Well-being Survey, real per-borough
                    # figures for every one of London's 33 boroughs (see
                    # build_wellbeing_index.py). All four measures are 0-10;
                    # anxiety is the only one where lower is better.
                    "wellbeing": {
                        "latest_year": wellbeing.get("latest_year"),
                        "life_satisfaction": wellbeing.get("life_satisfaction"),
                        "happiness": wellbeing.get("happiness"),
                        "worthwhile": wellbeing.get("worthwhile"),
                        "anxiety": wellbeing.get("anxiety"),
                        "life_satisfaction_trend": wellbeing.get("trend", {}).get("life-satisfaction", []),
                        "estimated": data['wellbeing_estimated'],
                    },
                    # GLA/ONS Price Index of Private Rents, Sep 2024-Aug 2025
                    # (see build_rent_index.py). affordability_score is 0-10,
                    # higher = cheaper relative to the rest of London.
                    "affordability_score": data['affordability'],
                    "rent": {
                        "typical_monthly": rent.get("typical_rent"),
                        "rent_1bed": rent.get("rent_1bed"),
                        "rent_2bed": rent.get("rent_2bed"),
                        "rent_3bed": rent.get("rent_3bed"),
                        "rent_4plusbed": rent.get("rent_4plusbed"),
                        "estimated": rent.get("estimated", False),
                    },
                    # English Indices of Deprivation 2025 (MHCLG), aggregated
                    # LSOA -> borough. Deciles: 1 = most deprived 10% in
                    # England, 10 = least deprived.
                    "imd": {
                        "overall_decile": dep['imd']['decile'],
                        "income_decile": dep['income']['decile'],
                        "employment_decile": dep['employment']['decile'],
                        "education_decile": dep['education']['decile'],
                        "health_decile": dep['health']['decile'],
                        "crime_decile": dep['crime']['decile'],
                        "housing_barriers_decile": barriers_decile,
                        "living_environment_decile": dep['living_environment']['decile'],
                        "population": data['deprivation']['population'],
                    }
                })

            rankings.sort(key=lambda x: x['overall_score'], reverse=True)
            self.send_json(rankings)
        elif parsed.path == '/api/lsoa-geo':
            # Static GeoJSON payload (4,994 London LSOA polygons + IMD 2025
            # domain deciles), served as-is and fetched lazily by the
            # frontend only when neighborhood view is switched on.
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write(LSOA_GEOJSON_BYTES)
        elif parsed.path == '/' or parsed.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_UI.encode('utf-8'))
        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>HappyBorough London — Legal Neighborhood Vibe & Happiness Index</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: #0F172A; color: #F8FAFC; height: 100vh; display: flex; flex-direction: column; }
        header { background: #1E293B; padding: 1rem 2rem; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 1.3rem; font-weight: 700; color: #10B981; display: flex; align-items: center; gap: 8px; }
        .badge { background: #065F46; color: #34D399; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
        .container { display: grid; grid-template-columns: 390px 1fr; flex: 1; overflow: hidden; }
        .sidebar { background: #1E293B; padding: 1.5rem; border-right: 1px solid #334155; overflow-y: auto; display: flex; flex-direction: column; gap: 1.2rem; }
        .card { background: #0F172A; border: 1px solid #334155; border-radius: 10px; padding: 1.2rem; }
        .slider-group { margin-bottom: 1rem; }
        .slider-label { display: flex; justify-content: space-between; font-size: 0.8rem; color: #CBD5E1; margin-bottom: 0.3rem; }
        input[type=range] { width: 100%; accent-color: #10B981; cursor: pointer; }
        #map { height: 100%; width: 100%; }
        .borough-item { padding: 0.85rem; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: background 0.15s; }
        .borough-item:hover { background: #1E293B; }
        .score-pill { background: #10B981; color: #064E3B; font-weight: 800; padding: 4px 10px; border-radius: 12px; font-size: 0.9rem; }
        .source-tag { font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; display: inline-block; margin-top: 3px; }
        .source-live { background: rgba(16, 185, 129, 0.2); color: #34D399; }
        .source-fallback { background: rgba(245, 158, 11, 0.2); color: #FBBF24; }
        .mode-btn { flex: 1; padding: 8px; background: #0F172A; color: #94A3B8; border: 1px solid #334155; border-radius: 6px; cursor: pointer; font-size: 0.78rem; font-weight: 600; }
        .mode-btn-active { background: #7C3AED; color: #FFFFFF; border-color: #7C3AED; }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            😊 HappyBorough London
            <span class="badge">🛡️ Live UK Police API + ONS Data Fusion</span>
        </div>
        <div style="font-size: 0.85rem; color: #94A3B8;">ONS Well-being + UK Police Open Data + TfL PTAL + IMD 2025 Deprivation (borough &amp; 4,994-LSOA) + GLA Private Rents + 181k Council Applications</div>
    </header>

    <div class="container">
        <div class="sidebar">
            <div class="card">
                <h3 style="font-size: 0.9rem; color: #38BDF8; margin-bottom: 1rem; text-transform: uppercase;">🎛️ Customize Your Happiness Priorities</h3>
                <div class="slider-group">
                    <div class="slider-label"><span>🛡️ Safety (Live Police API)</span><strong id="v-safety">20%</strong></div>
                    <input type="range" id="w-safety" min="0" max="100" value="20" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>🌳 Parks & Green Space</span><strong id="v-green">20%</strong></div>
                    <input type="range" id="w-green" min="0" max="100" value="20" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>🚆 Transport Accessibility</span><strong id="v-transport">15%</strong></div>
                    <input type="range" id="w-transport" min="0" max="100" value="15" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>😊 ONS Life Satisfaction</span><strong id="v-happiness">15%</strong></div>
                    <input type="range" id="w-happiness" min="0" max="100" value="15" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>🏘️ Housing & Service Barriers (IMD 2025)</span><strong id="v-barriers">15%</strong></div>
                    <input type="range" id="w-barriers" min="0" max="100" value="15" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>💷 Affordability (Private Rents)</span><strong id="v-affordability">15%</strong></div>
                    <input type="range" id="w-affordability" min="0" max="100" value="15" oninput="updateRankings()">
                </div>
            </div>

            <div class="card">
                <h3 style="font-size: 0.9rem; color: #A78BFA; margin-bottom: 0.8rem; text-transform: uppercase;">🗺️ Map View</h3>
                <div style="display: flex; gap: 6px; margin-bottom: 0.6rem;">
                    <button id="mode-borough" class="mode-btn mode-btn-active" onclick="setMapMode('borough')">🏙️ Boroughs</button>
                    <button id="mode-lsoa" class="mode-btn" onclick="setMapMode('lsoa')">🔬 Neighborhoods</button>
                </div>
                <div id="lsoa-controls" style="display: none;">
                    <select id="lsoa-domain" onchange="renderLsoaLayer()" style="width: 100%; padding: 6px; background: #0F172A; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; margin-bottom: 6px;">
                        <option value="imd">Overall Deprivation (IMD)</option>
                        <option value="income">Income</option>
                        <option value="employment">Employment</option>
                        <option value="education">Education, Skills & Training</option>
                        <option value="health">Health & Disability</option>
                        <option value="crime">Crime</option>
                        <option value="housing_barriers">Housing & Service Barriers</option>
                        <option value="living_environment">Living Environment</option>
                    </select>
                    <div style="font-size: 0.68rem; color: #94A3B8;">4,994 London LSOAs (IMD 2025) · decile 1 = most deprived, 10 = least deprived</div>
                </div>
            </div>

            <div class="card">
                <h3 style="font-size: 0.9rem; color: #10B981; margin-bottom: 0.8rem; text-transform: uppercase;">🏆 Top Matched Boroughs</h3>
                <div id="rankings-list">Loading legal open data rankings...</div>
            </div>
        </div>

        <div id="map"></div>
    </div>

    <script>
        let map = L.map('map').setView([51.5074, -0.1278], 11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map);
        let markersGroup = L.layerGroup().addTo(map);

        // --- LSOA neighborhood choropleth (lazy-loaded, IMD 2025) ---
        let mapMode = 'borough';
        let lsoaData = null;
        let lsoaLayer = null;

        // Decile 1 (most deprived) -> 10 (least deprived), red to green.
        const DECILE_COLORS = ['#7F1D1D', '#B91C1C', '#DC2626', '#EA580C', '#F59E0B', '#EAB308', '#84CC16', '#22C55E', '#16A34A', '#15803D'];
        function colorForDecile(decile) {
            if (decile === null || decile === undefined) return '#475569';
            const idx = Math.min(9, Math.max(0, Math.round(decile) - 1));
            return DECILE_COLORS[idx];
        }

        async function setMapMode(mode) {
            mapMode = mode;
            document.getElementById('mode-borough').classList.toggle('mode-btn-active', mode === 'borough');
            document.getElementById('mode-lsoa').classList.toggle('mode-btn-active', mode === 'lsoa');
            document.getElementById('lsoa-controls').style.display = mode === 'lsoa' ? 'block' : 'none';

            if (mode === 'borough') {
                if (lsoaLayer) map.removeLayer(lsoaLayer);
                if (!map.hasLayer(markersGroup)) map.addLayer(markersGroup);
            } else {
                if (map.hasLayer(markersGroup)) map.removeLayer(markersGroup);
                await renderLsoaLayer();
            }
        }

        async function renderLsoaLayer() {
            if (!lsoaData) {
                const res = await fetch('/api/lsoa-geo');
                lsoaData = await res.json();
            }
            if (lsoaLayer) map.removeLayer(lsoaLayer);

            const domain = document.getElementById('lsoa-domain').value;
            lsoaLayer = L.geoJSON(lsoaData, {
                style: (feature) => ({
                    fillColor: colorForDecile(feature.properties.domains[domain]?.decile),
                    fillOpacity: 0.65,
                    color: '#0F172A',
                    weight: 0.5,
                }),
                onEachFeature: (feature, layer) => {
                    const p = feature.properties;
                    const d = p.domains[domain];
                    layer.bindPopup(`
                        <strong>${p.lsoa_name}</strong><br/>
                        <small>${p.borough}</small><br/>
                        Decile: <b>${d ? d.decile : 'n/a'}/10</b> (1 = most deprived, 10 = least)<br/>
                        <small>LSOA code: ${p.lsoa_code}</small>
                    `);
                },
            }).addTo(map);
        }

        async function updateRankings() {
            const s = parseInt(document.getElementById('w-safety').value);
            const g = parseInt(document.getElementById('w-green').value);
            const t = parseInt(document.getElementById('w-transport').value);
            const h = parseInt(document.getElementById('w-happiness').value);
            const bar = parseInt(document.getElementById('w-barriers').value);
            const af = parseInt(document.getElementById('w-affordability').value);
            const total = s + g + t + h + bar + af || 1;

            document.getElementById('v-safety').innerText = Math.round((s/total)*100) + '%';
            document.getElementById('v-green').innerText = Math.round((g/total)*100) + '%';
            document.getElementById('v-transport').innerText = Math.round((t/total)*100) + '%';
            document.getElementById('v-happiness').innerText = Math.round((h/total)*100) + '%';
            document.getElementById('v-barriers').innerText = Math.round((bar/total)*100) + '%';
            document.getElementById('v-affordability').innerText = Math.round((af/total)*100) + '%';

            const res = await fetch(`/api/rankings?w_safety=${s/total}&w_green=${g/total}&w_transport=${t/total}&w_happiness=${h/total}&w_barriers=${bar/total}&w_affordability=${af/total}`);
            const data = await res.json();

            markersGroup.clearLayers();
            const listEl = document.getElementById('rankings-list');
            listEl.innerHTML = '';

            data.forEach((b, idx) => {
                const isLive = b.safety_source === 'live_api';
                const crimeDetail = b.recent_crimes !== null ? `(${b.recent_crimes} crimes reported this month)` : '(Benchmark fallback)';
                const estimatedNote = b.estimated_benchmark ? ' <small style="color:#FBBF24;">(London-avg estimate — no local green/transport benchmark)</small>' : '';
                const rentNote = b.rent.estimated ? ' <small style="color:#FBBF24;">(London-avg estimate — no ONS rent sample)</small>' : '';
                const wellbeingNote = b.wellbeing.estimated ? ' <small style="color:#FBBF24;">(London-avg estimate — sample too small for ONS to publish)</small>' : '';

                L.circleMarker([b.lat, b.lng], {
                    radius: 10 + (10 - idx),
                    fillColor: idx === 0 ? '#10B981' : (idx < 3 ? '#38BDF8' : '#F59E0B'),
                    color: '#FFFFFF',
                    weight: 2,
                    fillOpacity: 0.85
                }).bindPopup(`
                    <strong style="font-size: 1rem;">${b.borough}</strong><br/>
                    <b>Happiness Score:</b> ${b.overall_score}/100<br/>
                    🛡️ Safety: <b>${b.safety_score}/10</b> <small>${crimeDetail}</small><br/>
                    🌳 Green: ${b.green_space}/10 | 🚆 Transport: ${b.transport_score}/10${estimatedNote}<br/>
                    😊 ONS Life Satisfaction: ${b.wellbeing.life_satisfaction}/10 <small>(${b.wellbeing.latest_year || 'n/a'}, Happiness ${b.wellbeing.happiness}, Worthwhile ${b.wellbeing.worthwhile}, Anxiety ${b.wellbeing.anxiety})</small>${wellbeingNote}<br/>
                    💷 Affordability: <b>${b.affordability_score}/10</b> <small>(avg. rent £${Math.round(b.rent.typical_monthly).toLocaleString()}/mo)</small>${rentNote}<br/>
                    🏘️ Housing &amp; Services Barriers: <b>${b.imd.housing_barriers_decile}/10</b> decile (IMD 2025)<br/>
                    📉 Overall Deprivation Decile: ${b.imd.overall_decile}/10 · Health ${b.imd.health_decile}/10 · Education ${b.imd.education_decile}/10<br/>
                    👥 Population (IMD 2025): ${b.imd.population.toLocaleString()}<br/>
                    🏗️ Housing Approval Rate: ${b.housing_approval_rate}% (${b.housing_apps.toLocaleString()} apps)
                `).addTo(markersGroup);

                const item = document.createElement('div');
                item.className = 'borough-item';
                item.onclick = () => map.flyTo([b.lat, b.lng], 13);
                item.innerHTML = `
                    <div>
                        <div style="font-weight: 600; font-size: 0.9rem;">#${idx+1} ${b.borough}</div>
                        <div style="font-size: 0.73rem; color: #94A3B8;">
                            🛡️ Safety ${b.safety_score} · 🌳 Green ${b.green_space} · 🚆 Transit ${b.transport_score} · 🏘️ Barriers ${b.imd.housing_barriers_decile} · 💷 Afford. ${b.affordability_score}
                        </div>
                        <span class="source-tag ${isLive ? 'source-live' : 'source-fallback'}">
                            ${isLive ? `● Live Police API (${b.recent_crimes} crimes)` : '○ Benchmark Fallback'}
                        </span>
                        ${b.estimated_benchmark ? '<span class="source-tag source-fallback">○ Estimated green/transport</span>' : ''}
                        ${b.rent.estimated ? '<span class="source-tag source-fallback">○ Estimated rent</span>' : ''}
                        ${b.wellbeing.estimated ? '<span class="source-tag source-fallback">○ Estimated well-being</span>' : ''}
                    </div>
                    <div class="score-pill">${b.overall_score}</div>
                `;
                listEl.appendChild(item);
            });
        }

        updateRankings();
    </script>
</body>
</html>
"""

class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True


if __name__ == "__main__":
    warm_police_cache_async()
    # Threaded so a slow /api/rankings request (cold safety cache, live
    # police API fan-out across 33 boroughs) can't block page loads or other
    # concurrent requests -- a plain TCPServer handles one connection at a
    # time for its entire duration.
    server = ThreadingHTTPServer(("", PORT), HappinessHandler)
    print(f"😊 HappyBorough Server running with Live UK Police API at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
