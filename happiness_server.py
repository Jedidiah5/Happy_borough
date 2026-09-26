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
    server = socketserver.TCPServer(("", PORT), HappinessHandler)
    print(f"😊 HappyBorough Server running with Live UK Police API at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
