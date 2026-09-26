import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import sqlite3
import os
import time
import threading

PORT = int(os.environ.get('PORT', 8085))
DB_PATH = 'housing.db'

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
    </style>
</head>
<body>
    <header>
        <div class="logo">
            😊 HappyBorough London
            <span class="badge">🛡️ Live UK Police API + ONS Data Fusion</span>
        </div>
        <div style="font-size: 0.85rem; color: #94A3B8;">ONS Well-being + UK Police Open Data + TfL PTAL + 181k Council Applications</div>
    </header>

    <div class="container">
        <div class="sidebar">
            <div class="card">
                <h3 style="font-size: 0.9rem; color: #38BDF8; margin-bottom: 1rem; text-transform: uppercase;">🎛️ Customize Your Happiness Priorities</h3>
                <div class="slider-group">
                    <div class="slider-label"><span>🛡️ Safety (Live Police API)</span><strong id="v-safety">30%</strong></div>
                    <input type="range" id="w-safety" min="0" max="100" value="30" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>🌳 Parks & Green Space</span><strong id="v-green">30%</strong></div>
                    <input type="range" id="w-green" min="0" max="100" value="30" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>🚆 Transport Accessibility</span><strong id="v-transport">20%</strong></div>
                    <input type="range" id="w-transport" min="0" max="100" value="20" oninput="updateRankings()">
                </div>
                <div class="slider-group">
                    <div class="slider-label"><span>😊 ONS Community Satisfaction</span><strong id="v-happiness">20%</strong></div>
                    <input type="range" id="w-happiness" min="0" max="100" value="20" oninput="updateRankings()">
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

        async function updateRankings() {
            const s = parseInt(document.getElementById('w-safety').value);
            const g = parseInt(document.getElementById('w-green').value);
            const t = parseInt(document.getElementById('w-transport').value);
            const h = parseInt(document.getElementById('w-happiness').value);
            const total = s + g + t + h || 1;

            document.getElementById('v-safety').innerText = Math.round((s/total)*100) + '%';
            document.getElementById('v-green').innerText = Math.round((g/total)*100) + '%';
            document.getElementById('v-transport').innerText = Math.round((t/total)*100) + '%';
            document.getElementById('v-happiness').innerText = Math.round((h/total)*100) + '%';

            const res = await fetch(`/api/rankings?w_safety=${s/total}&w_green=${g/total}&w_transport=${t/total}&w_happiness=${h/total}`);
            const data = await res.json();

            markersGroup.clearLayers();
            const listEl = document.getElementById('rankings-list');
            listEl.innerHTML = '';

            data.forEach((b, idx) => {
                const isLive = b.safety_source === 'live_api';
                const crimeDetail = b.recent_crimes !== null ? `(${b.recent_crimes} crimes reported this month)` : '(Benchmark fallback)';
                
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
                    🌳 Green: ${b.green_space}/10 | 🚆 Transport: ${b.transport_score}/10<br/>
                    😊 ONS Happiness Rating: ${b.ons_happiness}/10<br/>
                    🏗️ Housing Approval Rate: ${b.housing_approval_rate}% (${b.housing_apps.toLocaleString()} apps)
                `).addTo(markersGroup);

                const item = document.createElement('div');
                item.className = 'borough-item';
                item.onclick = () => map.flyTo([b.lat, b.lng], 13);
                item.innerHTML = `
                    <div>
                        <div style="font-weight: 600; font-size: 0.9rem;">#${idx+1} ${b.borough}</div>
                        <div style="font-size: 0.73rem; color: #94A3B8;">
                            🛡️ Safety ${b.safety_score} · 🌳 Green ${b.green_space} · 🚆 Transit ${b.transport_score}
                        </div>
                        <span class="source-tag ${isLive ? 'source-live' : 'source-fallback'}">
                            ${isLive ? `● Live Police API (${b.recent_crimes} crimes)` : '○ Benchmark Fallback'}
                        </span>
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

if __name__ == "__main__":
    warm_police_cache_async()
    server = socketserver.TCPServer(("", PORT), HappinessHandler)
    print(f"😊 HappyBorough Server running with Live UK Police API at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
