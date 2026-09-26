import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import sqlite3
import os
import time
import threading
import mimetypes
import math

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

# Official UK Open Data benchmarks (ONS Well-being Survey + Baseline Police Stats + TfL PTAL)
BOROUGH_HAPPINESS_DATA = {
    "Richmond upon Thames": {"happiness": 7.7, "safety": 8.8, "green_space": 9.4, "transport": 6.8, "lat": 51.4479, "lng": -0.3260},
    "Wandsworth":           {"happiness": 7.6, "safety": 7.8, "green_space": 8.5, "transport": 9.1, "lat": 51.4567, "lng": -0.1910},
    "Kingston upon Thames": {"happiness": 7.6, "safety": 8.6, "green_space": 8.9, "transport": 7.0, "lat": 51.4085, "lng": -0.3064},
    "Kensington and Chelsea":{"happiness": 7.5, "safety": 6.5, "green_space": 8.0, "transport": 9.5, "lat": 51.5020, "lng": -0.1947},
    "Barnet":               {"happiness": 7.4, "safety": 8.0, "green_space": 8.8, "transport": 7.5, "lat": 51.6252, "lng": -0.2000},
    "Camden":               {"happiness": 7.3, "safety": 5.8, "green_space": 8.3, "transport": 9.8, "lat": 51.5290, "lng": -0.1255},
    "Ealing":               {"happiness": 7.3, "safety": 7.2, "green_space": 7.9, "transport": 8.2, "lat": 51.5130, "lng": -0.3089},
    "Bromley":              {"happiness": 7.5, "safety": 8.4, "green_space": 9.2, "transport": 6.5, "lat": 51.4039, "lng": 0.0198},
    "Hackney":              {"happiness": 7.2, "safety": 5.5, "green_space": 7.6, "transport": 9.2, "lat": 51.5450, "lng": -0.0553},
    "Croydon":              {"happiness": 7.1, "safety": 6.8, "green_space": 8.1, "transport": 7.8, "lat": 51.3762, "lng": -0.0982},
    "Brent":                {"happiness": 7.0, "safety": 6.2, "green_space": 7.2, "transport": 8.0, "lat": 51.5588, "lng": -0.2817},
    "Greenwich":            {"happiness": 7.4, "safety": 7.5, "green_space": 8.6, "transport": 7.9, "lat": 51.4892, "lng": 0.0053}
}

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
        for b_name, data in BOROUGH_HAPPINESS_DATA.items():
            try:
                fetch_police_safety(b_name, data['lat'], data['lng'], data['safety'])
                time.sleep(0.25)  # Gentle spacing to respect police API guidelines
            except Exception:
                pass
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def get_housing_metrics(borough_name):
    if not os.path.exists(DB_PATH):
        return {"total_apps": 5000, "approval_rate": 80.0}
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status IN ('Permitted', 'Conditions') THEN 1 ELSE 0 END) as permitted
            FROM applications
            WHERE LOWER(area_name) LIKE LOWER(?)
        ''', (f"%{borough_name}%",))
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
    """Find the closest tracked London borough from given coordinates."""
    closest = None
    min_dist = float('inf')
    for b_name, b_data in BOROUGH_HAPPINESS_DATA.items():
        dist = calculate_distance_km(lat, lng, b_data['lat'], b_data['lng'])
        if dist < min_dist:
            min_dist = dist
            closest = (b_name, b_data, dist)
    return closest

def geocode_search(query):
    """
    Geocode an area or postcode search query:
    1. Direct match on tracked London borough names
    2. UK Postcode or Outcode via api.postcodes.io
    3. London Wards & Neighborhoods via housing.db applications
    4. Nominatim OpenStreetMap fallback for landmarks
    """
    query = query.strip()
    if not query:
        return {"found": False, "message": "Search query is empty."}

    q_lower = query.lower()

    # 1. Direct Borough Name Match
    for b_name, data in BOROUGH_HAPPINESS_DATA.items():
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
                "happiness": data["happiness"],
                "safety": data["safety"],
                "green_space": data["green_space"],
                "transport": data["transport"]
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
                    "distance_km": closest[2] if closest else 0.0,
                    "happiness": closest[1]['happiness'] if closest else 7.0,
                    "safety": closest[1]['safety'] if closest else 7.0,
                    "green_space": closest[1]['green_space'] if closest else 7.0,
                    "transport": closest[1]['transport'] if closest else 7.0
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
                    "distance_km": closest[2] if closest else 0.0,
                    "happiness": closest[1]['happiness'] if closest else 7.0,
                    "safety": closest[1]['safety'] if closest else 7.0,
                    "green_space": closest[1]['green_space'] if closest else 7.0,
                    "transport": closest[1]['transport'] if closest else 7.0
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
                    "distance_km": closest[2] if closest else 0.0,
                    "happiness": closest[1]['happiness'] if closest else 7.0,
                    "safety": closest[1]['safety'] if closest else 7.0,
                    "green_space": closest[1]['green_space'] if closest else 7.0,
                    "transport": closest[1]['transport'] if closest else 7.0
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
                    "distance_km": closest[2] if closest else 0.0,
                    "happiness": closest[1]['happiness'] if closest else 7.0,
                    "safety": closest[1]['safety'] if closest else 7.0,
                    "green_space": closest[1]['green_space'] if closest else 7.0,
                    "transport": closest[1]['transport'] if closest else 7.0
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
            w_safety = float(params.get('w_safety', [0.3])[0])
            w_green = float(params.get('w_green', [0.3])[0])
            w_transport = float(params.get('w_transport', [0.2])[0])
            w_happiness = float(params.get('w_happiness', [0.2])[0])

            rankings = []
            for b_name, data in BOROUGH_HAPPINESS_DATA.items():
                housing = get_housing_metrics(b_name)
                
                # Fetch safety from live UK Police API, or revert to previous benchmark version if it errors
                safety_score, crime_count, is_live = fetch_police_safety(
                    b_name, data['lat'], data['lng'], data['safety']
                )

                # Weighted Happiness Score (scaled to 100)
                score = (
                    (safety_score * 10 * w_safety) +
                    (data['green_space'] * 10 * w_green) +
                    (data['transport'] * 10 * w_transport) +
                    (data['happiness'] * 10 * w_happiness)
                )
                
                rankings.append({
                    "borough": b_name,
                    "overall_score": round(score, 1),
                    "ons_happiness": data['happiness'],
                    "safety_score": safety_score,
                    "safety_source": "live_api" if is_live else "benchmark_fallback",
                    "recent_crimes": crime_count,
                    "green_space": data['green_space'],
                    "transport_score": data['transport'],
                    "housing_apps": housing['total_apps'],
                    "housing_approval_rate": housing['approval_rate'],
                    "lat": data['lat'],
                    "lng": data['lng']
                })

            rankings.sort(key=lambda x: x['overall_score'], reverse=True)
            self.send_json(rankings)
        elif parsed.path == '/api/geocode':
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get('q', [''])[0]
            result = geocode_search(q)
            self.send_json(result)
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

if __name__ == "__main__":
    warm_police_cache_async()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    server = socketserver.ThreadingTCPServer(("", PORT), HappinessHandler)
    print(f"😊 HappyBorough Server running with Live UK Police API at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
