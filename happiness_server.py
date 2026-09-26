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
import mimetypes
import math
import concurrent.futures

# Some Windows terminals default stdout to a legacy codepage (cp1252) that
# can't encode the emoji in this file's log messages; force UTF-8 so the
# server doesn't crash on startup in those environments.
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PORT = int(os.environ.get('PORT', 8085))
DB_PATH = 'housing.db'
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
# Explicit types: Windows registry can map .js to text/plain.
STATIC_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
}
DEPRIVATION_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'deprivation_borough.json')
WELLBEING_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'wellbeing_borough.json')
RENT_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'rent_borough.json')
GREENSPACE_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'greenspace_borough.json')
TRANSPORT_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'transport_borough.json')
LSOA_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'lsoa_choropleth.json')

# Baseline Police Stats benchmark. Only available for a subset of boroughs
# (the ones with a hand-curated published figure) -- every other borough
# falls back to the IMD Crime domain decile (see build_borough_registry).
# (Real, per-borough ONS well-being data for 32 of 33 boroughs comes from
# WELLBEING_DATA below -- see build_wellbeing_index.py. green_space here is
# unused -- real per-borough figures for all 33 boroughs come from
# GREENSPACE_DATA instead -- see build_greenspace_index.py. Transport used to
# live here too as a hand-typed guess, but now comes from TRANSPORT_DATA for
# all 33 boroughs -- see build_transport_index.py.)
BOROUGH_HAPPINESS_DATA = {
    "Richmond upon Thames": {"safety": 8.8, "green_space": 9.4, "lat": 51.4479, "lng": -0.3260},
    "Wandsworth":           {"safety": 7.8, "green_space": 8.5, "lat": 51.4567, "lng": -0.1910},
    "Kingston upon Thames": {"safety": 8.6, "green_space": 8.9, "lat": 51.4085, "lng": -0.3064},
    "Kensington and Chelsea":{"safety": 6.5, "green_space": 8.0, "lat": 51.5020, "lng": -0.1947},
    "Barnet":               {"safety": 8.0, "green_space": 8.8, "lat": 51.6252, "lng": -0.2000},
    "Camden":               {"safety": 5.8, "green_space": 8.3, "lat": 51.5290, "lng": -0.1255},
    "Ealing":               {"safety": 7.2, "green_space": 7.9, "lat": 51.5130, "lng": -0.3089},
    "Bromley":              {"safety": 8.4, "green_space": 9.2, "lat": 51.4039, "lng": 0.0198},
    "Hackney":              {"safety": 5.5, "green_space": 7.6, "lat": 51.5450, "lng": -0.0553},
    "Croydon":              {"safety": 6.8, "green_space": 8.1, "lat": 51.3762, "lng": -0.0982},
    "Brent":                {"safety": 6.2, "green_space": 7.2, "lat": 51.5588, "lng": -0.2817},
    "Greenwich":            {"safety": 7.5, "green_space": 8.6, "lat": 51.4892, "lng": 0.0053}
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

# Real OS Open Greenspace figures for all 33 boroughs (green space area as a
# % of borough land area, normalized to a 0-10 score), built by
# build_greenspace_index.py from data/os_greenspace_borough_raw.csv. Replaces
# the old 12-borough curated/estimated split for green space -- OS's national
# coverage means every borough gets a genuine, sourced figure here.
GREENSPACE_DATA = load_json_data(GREENSPACE_JSON_PATH, "OS Open Greenspace data")

# Real TfL Public Transport Accessibility Level (PTAL) data for all 33
# boroughs, population-weighted up from ward level, built by
# build_transport_index.py from data/tfl_ward_ptal_2023.geojson. Replaces the
# old approach of hand-typing a 0-10 guess for 12 boroughs and averaging
# those 12 for the rest -- transport is now sourced exactly like every other
# metric in this app.
TRANSPORT_DATA = load_json_data(TRANSPORT_JSON_PATH, "TfL PTAL transport data")

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

# London-wide average of the ONS well-being measures, used as a neutral
# stand-in for the one borough that doesn't have its own figure (flagged as
# "estimated" in the API response so the UI can be honest about it). The
# City of London's population (~8,000) is too small for ONS to publish a
# reliable well-being estimate for any measure, so it's the one borough that
# needs this fallback for happiness. (Green space and transport both have
# real per-borough data for all 33 boroughs now -- GREENSPACE_DATA and
# TRANSPORT_DATA -- so neither needs a London-average fallback any more.)
LONDON_AVERAGE = {
    "wellbeing": {
        measure: round(sum(v for v in values if v is not None) / len([v for v in values if v is not None]), 2)
        for measure in ("life_satisfaction", "happiness", "worthwhile", "anxiety")
        for values in [[b.get(measure) for b in WELLBEING_DATA.values()]]
    },
}


def build_borough_registry():
    """
    Full 33-borough registry: starts from IMD 2025 coverage (all London
    boroughs) and layers real OS Open Greenspace data, real TfL PTAL
    transport data, real ONS well-being data, and real rent/affordability
    data on top -- falling back to a flagged London-wide average only for
    the City of London's well-being/rent (population too small for ONS to
    publish). Green space and transport both have a real per-borough figure
    for all 33 boroughs, so neither needs a fallback any more.
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
        greenspace = GREENSPACE_DATA.get(name, {})
        transport = TRANSPORT_DATA.get(name, {})
        registry[name] = {
            "lat": coords["lat"],
            "lng": coords["lng"],
            "happiness": wellbeing.get("life_satisfaction"),
            "wellbeing": wellbeing,
            "wellbeing_estimated": wellbeing_estimated,
            "green_space": greenspace.get("green_space_score", 5.0),
            "greenspace": greenspace,
            "transport": transport.get("transport_score", 5.0),
            "transport_detail": transport,
            # Fallback used only if the live Police API call fails: prefer
            # the curated benchmark, otherwise derive one from IMD's Crime
            # domain decile (already on a comparable 1-10, higher-is-safer scale).
            "safety": curated["safety"] if curated else round(crime_decile, 1),
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

def calculate_distance_km(lat1, lng1, lat2, lng2):
    """Haversine distance between two coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def find_closest_borough(lat, lng):
    """Find the closest of all 33 tracked London boroughs to given coordinates."""
    closest = None
    min_dist = float('inf')
    for b_name, b_data in BOROUGH_REGISTRY.items():
        dist = calculate_distance_km(lat, lng, b_data['lat'], b_data['lng'])
        if dist < min_dist:
            min_dist = dist
            closest = (b_name, dist)
    return closest

def geocode_search(query):
    """
    Geocode an area or postcode search query to the closest of the 33
    tracked London boroughs:
    1. Direct match on tracked London borough names
    2. UK Postcode or Outcode via api.postcodes.io
    3. London Wards & Neighborhoods via housing.db applications
    4. Nominatim OpenStreetMap fallback for landmarks

    Only returns match/location info, not borough metrics -- the frontend
    already has every borough's full, real metric set from /api/rankings, so
    it looks up result['borough'] there instead of this endpoint duplicating
    (and risking staling) those scores.
    """
    query = query.strip()
    if not query:
        return {"found": False, "message": "Search query is empty."}

    q_lower = query.lower()

    # 1. Direct Borough Name Match
    for b_name, data in BOROUGH_REGISTRY.items():
        if q_lower == b_name.lower() or (len(q_lower) >= 3 and q_lower in b_name.lower()):
            return {
                "found": True,
                "type": "borough",
                "query": query,
                "matched_name": b_name,
                "borough": b_name,
                "district": b_name,
                "lat": data["lat"],
                "lng": data["lng"],
                "distance_km": 0.0,
            }

    # 2. UK Postcode or Outcode Lookup via api.postcodes.io
    clean_pc = urllib.parse.quote(query.replace(" ", "").upper())
    try:
        url = f"https://api.postcodes.io/postcodes/{clean_pc}"
        req = urllib.request.Request(url, headers={'User-Agent': 'HappyBorough-App/1.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 200 and 'result' in data:
                r = data['result']
                lat = r.get('latitude')
                lng = r.get('longitude')
                distr = r.get('admin_district') or r.get('parish') or 'London'
                closest = find_closest_borough(lat, lng)
                return {
                    "found": True,
                    "type": "postcode",
                    "query": query,
                    "matched_name": f"{query.upper()} ({distr})",
                    "borough": closest[0] if closest else distr,
                    "district": distr,
                    "lat": lat,
                    "lng": lng,
                    "distance_km": closest[1] if closest else 0.0,
                }
    except Exception:
        pass

    try:
        url = f"https://api.postcodes.io/outcodes/{clean_pc}"
        req = urllib.request.Request(url, headers={'User-Agent': 'HappyBorough-App/1.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 200 and 'result' in data:
                r = data['result']
                lat = r.get('latitude')
                lng = r.get('longitude')
                districts = r.get('admin_district') or []
                distr_str = ", ".join(districts) if isinstance(districts, list) else str(districts)
                closest = find_closest_borough(lat, lng)
                return {
                    "found": True,
                    "type": "postcode_outcode",
                    "query": query,
                    "matched_name": f"{query.upper()} ({distr_str})",
                    "borough": closest[0] if closest else (districts[0] if districts else "London"),
                    "district": distr_str,
                    "lat": lat,
                    "lng": lng,
                    "distance_km": closest[1] if closest else 0.0,
                }
    except Exception:
        pass

    # 3. Database Search in housing.db (London Wards and Area names)
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                SELECT ward_name, area_name, AVG(lat), AVG(lng), COUNT(*) as cnt
                FROM applications
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND (LOWER(ward_name) LIKE ? OR LOWER(area_name) LIKE ?)
                GROUP BY ward_name, area_name
                ORDER BY cnt DESC
                LIMIT 1
            ''', (f"%{q_lower}%", f"%{q_lower}%"))
            row = c.fetchone()
            conn.close()
            if row and row[2] and row[3]:
                ward_name, area_name, lat, lng, cnt = row
                closest = find_closest_borough(lat, lng)
                display = f"{ward_name}, {area_name}" if ward_name and ward_name != area_name else area_name
                return {
                    "found": True,
                    "type": "area",
                    "query": query,
                    "matched_name": display,
                    "borough": closest[0] if closest else area_name,
                    "district": area_name,
                    "lat": round(lat, 5),
                    "lng": round(lng, 5),
                    "distance_km": closest[1] if closest else 0.0,
                }
        except Exception as e:
            print(f"DB geocode lookup note: {e}")

    # 4. Fallback: OpenStreetMap Nominatim for London landmarks
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query + ', London, UK')}&format=json&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'HappyBorough-App/1.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                first = data[0]
                lat = float(first['lat'])
                lng = float(first['lon'])
                display_name = first.get('display_name', query).split(',')[0]
                closest = find_closest_borough(lat, lng)
                return {
                    "found": True,
                    "type": "location",
                    "query": query,
                    "matched_name": f"{display_name} (London)",
                    "borough": closest[0] if closest else "London",
                    "district": "London",
                    "lat": round(lat, 5),
                    "lng": round(lng, 5),
                    "distance_km": closest[1] if closest else 0.0,
                }
    except Exception:
        pass

    return {
        "found": False,
        "query": query,
        "message": f"Could not find coordinates for '{query}'. Try a London borough (e.g. Richmond), ward (e.g. Mayesbrook), or UK postcode (e.g. SW1A 1AA, CR0)."
    }

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
                    "safety_score": safety_score,
                    "safety_source": "live_api" if is_live else "benchmark_fallback",
                    "recent_crimes": crime_count,
                    "green_space": data['green_space'],
                    # OS Open Greenspace (see build_greenspace_index.py):
                    # green_space_pct is the borough's land area covered by a
                    # mapped greenspace site; real for all 33 boroughs, so
                    # never estimated.
                    "green_space_pct": data['greenspace'].get('green_space_pct'),
                    "green_space_sites": data['greenspace'].get('site_count'),
                    "transport_score": data['transport'],
                    "housing_apps": housing['total_apps'],
                    "housing_approval_rate": housing['approval_rate'],
                    "lat": data['lat'],
                    "lng": data['lng'],
                    # TfL Public Transport Accessibility Level (PTAL), real
                    # per-borough figure for all 33 boroughs, population-
                    # weighted up from ward level (see
                    # build_transport_index.py). transport_score above is
                    # this rescaled 0-10 across the 33 boroughs; mean_ai is
                    # the raw, unbounded Accessibility Index it's derived
                    # from, and ptal_band is TfL's official 0/1a-6b banding.
                    "transport": {
                        "mean_accessibility_index": data['transport_detail'].get('mean_accessibility_index'),
                        "ptal_band": data['transport_detail'].get('ptal_band'),
                    },
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
        elif parsed.path == '/api/geocode':
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get('q', [''])[0]
            result = geocode_search(q)
            self.send_json(result)
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
            self.send_static_file(os.path.join(STATIC_DIR, 'happy', 'index.html'))
        elif parsed.path.startswith('/static/'):
            rel_path = urllib.parse.unquote(parsed.path[len('/static/'):])
            self.send_static_file(os.path.join(STATIC_DIR, rel_path))
        else:
            self.send_error(404)

    def send_static_file(self, file_path):
        static_root = os.path.realpath(STATIC_DIR)
        full_path = os.path.realpath(file_path)
        if not full_path.startswith(static_root + os.sep) or not os.path.isfile(full_path):
            self.send_error(404)
            return
        ext = os.path.splitext(full_path)[1].lower()
        ctype = STATIC_TYPES.get(ext) or mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
        with open(full_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


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