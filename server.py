import http.server
import socketserver
import json
import sqlite3
import urllib.parse
import os
import math

PORT = int(os.environ.get('PORT', 8080))
DB_PATH = 'housing.db'

def load_env():
    """Load key-value pairs from .env if present."""
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception as e:
            print(f"Warning loading .env: {e}")

load_env()

def query_db(query, params=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"Database query note: {e}")
        return []

class PlanPulseHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == '/api/boroughs':
            self.send_json(self.get_borough_benchmarks())
        elif path == '/api/predict':
            b = params.get('borough', ['Croydon'])[0]
            sz = params.get('app_size', ['Small'])[0]
            kw = params.get('keyword', [''])[0]
            self.send_json(self.predict_risk(b, sz, kw))
        elif path == '/api/precedents':
            try:
                lat = float(params.get('lat', [51.5074])[0])
                lng = float(params.get('lng', [-0.1278])[0])
                kw = params.get('keyword', [''])[0]
                rad = float(params.get('radius', [2.5])[0])
                limit = int(params.get('limit', [25])[0])
                self.send_json(self.search_precedents(lat, lng, kw, rad, limit))
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        elif path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            token = os.environ.get('MAPBOX_ACCESS_TOKEN', '')
            rendered_ui = HTML_UI.replace('__MAPBOX_ENV_TOKEN__', token)
            self.wfile.write(rendered_ui.encode('utf-8'))
        else:
            self.send_error(404, "Page not found")

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def get_borough_benchmarks(self):
        rows = query_db('''
            SELECT area_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN status IN ('Permitted', 'Conditions') THEN 1 ELSE 0 END) as permitted,
                   SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected,
                   AVG(days_to_decision) as avg_days,
                   SUM(n_dwellings) as total_dwellings,
                   AVG(lat) as avg_lat,
                   AVG(lng) as avg_lng
            FROM applications
            WHERE area_name IS NOT NULL AND area_name != ''
            GROUP BY area_name
            ORDER BY total DESC
        ''')
        out = []
        for r in rows:
            t = r['total']
            rej = r['rejected'] or 0
            perm = r['permitted'] or 0
            out.append({
                "borough": r['area_name'],
                "total": t,
                "permitted": perm,
                "rejected": rej,
                "rejection_rate": round((rej / t * 100), 1) if t else 0,
                "approval_rate": round((perm / t * 100), 1) if t else 0,
                "avg_days": round(r['avg_days'], 1) if r['avg_days'] else 56.0,
                "dwellings": int(r['total_dwellings'] or 0),
                "lat": round(r['avg_lat'], 4) if r['avg_lat'] else 51.5074,
                "lng": round(r['avg_lng'], 4) if r['avg_lng'] else -0.1278
            })
        return out

    def predict_risk(self, borough, app_size, keyword):
        sql = "SELECT status, days_to_decision FROM applications WHERE LOWER(area_name) = LOWER(?)"
        params = [borough]
        if app_size and app_size != 'All':
            sql += " AND LOWER(app_size) = LOWER(?)"
            params.append(app_size)
        if keyword:
            sql += " AND description LIKE ?"
            params.append(f"%{keyword}%")
            
        rows = query_db(sql, params)
        if not rows:
            return {"sample_size": 0, "approval_probability": 75.0, "risk_level": "MEDIUM RISK", "risk_color": "#F59E0B", "rejection_risk": 25.0, "estimated_days": 56.0}
            
        total = len(rows)
        permitted = sum(1 for r in rows if r['status'] in ('Permitted', 'Conditions'))
        rejected = sum(1 for r in rows if r['status'] == 'Rejected')
        days_list = [r['days_to_decision'] for r in rows if r['days_to_decision'] is not None and 0 <= r['days_to_decision'] <= 365]
        
        prob = round((permitted / total * 100), 1)
        rej_risk = round((rejected / total * 100), 1)
        avg_days = round(sum(days_list) / len(days_list), 1) if days_list else 56.0
        
        if prob >= 80:
            level = "LOW RISK"
            color = "#10B981"
        elif prob >= 65:
            level = "MEDIUM RISK"
            color = "#F59E0B"
        else:
            level = "HIGH RISK"
            color = "#EF4444"

        return {
            "borough": borough,
            "app_size": app_size,
            "keyword": keyword,
            "sample_size": total,
            "approval_probability": prob,
            "rejection_risk": rej_risk,
            "risk_level": level,
            "risk_color": color,
            "estimated_days": avg_days
        }

    def search_precedents(self, lat, lng, keyword, radius_km, limit):
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / 69.0
        
        sql = '''
            SELECT name, area_name, status, decision, days_to_decision, url, description, app_size, app_type, lat, lng, n_dwellings,
                   ((lat - ?)*(lat - ?) + (lng - ?)*(lng - ?)) as dist
            FROM applications
            WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
        '''
        params = [lat, lat, lng, lng, lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta]
        if keyword:
            sql += " AND description LIKE ?"
            params.append(f"%{keyword}%")
        sql += " ORDER BY dist ASC LIMIT ?"
        params.append(limit)
        
        return query_db(sql, params)

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PlanPulse London — Mapbox 3D AI Planning Risk & Precedent Engine</title>
    <!-- Mapbox GL JS v3 -->
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.2.0/mapbox-gl.css" rel="stylesheet" />
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.2.0/mapbox-gl.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0B0F17;
            --bg-surface: #111827;
            --bg-card: #182234;
            --border-color: #243247;
            --border-highlight: #334863;
            --text-primary: #F8FAFC;
            --text-secondary: #94A3B8;
            --text-muted: #64748B;
            --accent-cyan: #38BDF8;
            --accent-blue: #0284C7;
            --accent-green: #10B981;
            --accent-red: #EF4444;
            --accent-amber: #F59E0B;
            --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-sans); }
        body { background-color: var(--bg-base); color: var(--text-primary); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

        /* Top Header */
        header {
            background: linear-gradient(180deg, #111827 0%, #0F172A 100%);
            padding: 0.85rem 1.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            z-index: 100;
        }
        .header-left { display: flex; align-items: center; gap: 14px; }
        .logo { font-size: 1.35rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 10px; letter-spacing: -0.5px; }
        .logo-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #0284C7 0%, #38BDF8 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
            box-shadow: 0 0 15px rgba(56, 189, 248, 0.35);
        }
        .badge { background: rgba(2, 132, 199, 0.2); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .header-right { display: flex; align-items: center; gap: 16px; }
        .stat-pill { font-size: 0.82rem; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
        .stat-count { font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600; }

        /* Mapbox Status Pill */
        .token-badge-btn {
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 7px;
            transition: all 0.2s ease;
        }
        .token-badge-btn:hover { border-color: var(--accent-cyan); background: rgba(51, 65, 85, 0.9); }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        .token-badge-btn.connected .status-dot { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }
        .token-badge-btn.disconnected .status-dot { background: var(--accent-amber); box-shadow: 0 0 8px var(--accent-amber); }

        /* App Layout */
        .container { display: grid; grid-template-columns: 400px 1fr; flex: 1; overflow: hidden; position: relative; }

        /* Sidebar */
        .sidebar {
            background: var(--bg-surface);
            padding: 1.25rem;
            border-right: 1px solid var(--border-color);
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1.15rem;
            scrollbar-width: thin;
            scrollbar-color: var(--border-color) transparent;
        }
        .sidebar::-webkit-scrollbar { width: 6px; }
        .sidebar::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.15rem;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
            transition: border-color 0.2s ease;
        }
        .card:hover { border-color: var(--border-highlight); }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.9rem;
        }
        .card h3 {
            font-size: 0.88rem;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .form-group { margin-bottom: 0.85rem; }
        label { display: block; font-size: 0.78rem; font-weight: 600; color: #CBD5E1; margin-bottom: 0.35rem; }
        select, input[type="text"] {
            width: 100%;
            padding: 0.65rem 0.8rem;
            background: #0F172A;
            border: 1px solid #334155;
            border-radius: 8px;
            color: white;
            font-size: 0.88rem;
            transition: all 0.2s ease;
        }
        select:focus, input[type="text"]:focus {
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
        }

        /* Quick keyword chips */
        .kw-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 0.45rem;
        }
        .kw-chip {
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            color: #94A3B8;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .kw-chip:hover {
            border-color: var(--accent-cyan);
            color: #FFFFFF;
            background: rgba(2, 132, 199, 0.25);
        }

        .btn-primary {
            width: 100%;
            padding: 0.8rem;
            background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.92rem;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
            margin-top: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.35);
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #0369A1 0%, #0284C7 100%);
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(2, 132, 199, 0.45);
        }
        .btn-primary:active { transform: translateY(0); }

        /* Metric Grid */
        .metric-row { display: flex; justify-content: space-between; align-items: center; margin-top: 0.4rem; }
        .metric-val { font-size: 2.1rem; font-weight: 800; font-family: var(--font-mono); letter-spacing: -0.5px; }
        .risk-badge {
            padding: 5px 12px;
            border-radius: 8px;
            font-weight: 800;
            font-size: 0.8rem;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .metric-subgrid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 1rem;
            padding-top: 0.85rem;
            border-top: 1px solid #243247;
        }
        .metric-mini-box {
            background: #0F172A;
            border: 1px solid #243247;
            border-radius: 8px;
            padding: 8px 10px;
        }
        .mini-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 2px; }
        .mini-val { font-size: 0.95rem; font-family: var(--font-mono); font-weight: 700; color: #E2E8F0; }

        /* Map Container */
        #map-container { position: relative; height: 100%; width: 100%; background: #080D14; }
        #map { height: 100%; width: 100%; }

        /* Mapbox Floating Controls */
        .map-style-bar {
            position: absolute;
            top: 16px;
            left: 16px;
            z-index: 10;
            display: flex;
            align-items: center;
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 4px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            gap: 3px;
        }
        .style-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 0.76rem;
            font-weight: 700;
            padding: 6px 11px;
            border-radius: 7px;
            cursor: pointer;
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .style-btn:hover { color: #FFFFFF; background: rgba(51, 65, 85, 0.5); }
        .style-btn.active {
            background: var(--accent-blue);
            color: #FFFFFF;
            box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
        }

        .map-tools-bar {
            position: absolute;
            top: 16px;
            right: 56px;
            z-index: 10;
            display: flex;
            gap: 8px;
        }
        .tool-btn {
            background: rgba(17, 24, 39, 0.9);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            font-size: 0.78rem;
            font-weight: 700;
            padding: 7px 12px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 8px 20px rgba(0,0,0,0.4);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .tool-btn:hover { border-color: var(--accent-cyan); background: rgba(30, 41, 59, 0.95); }
        .tool-btn.active { background: rgba(2, 132, 199, 0.35); border-color: var(--accent-cyan); color: var(--accent-cyan); }

        /* Floating Precedents Results Drawer */
        .results-panel {
            position: absolute;
            bottom: 24px;
            right: 24px;
            width: 440px;
            max-height: 480px;
            background: rgba(17, 24, 39, 0.95);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
            display: flex;
            flex-direction: column;
            z-index: 15;
            overflow: hidden;
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .panel-header {
            padding: 1rem 1.2rem;
            background: rgba(15, 23, 42, 0.9);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .panel-header h4 {
            font-size: 0.92rem;
            font-weight: 700;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .panel-count {
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-cyan);
            font-family: var(--font-mono);
            font-size: 0.78rem;
            padding: 3px 8px;
            border-radius: 12px;
            font-weight: 700;
        }
        .precedents-list {
            padding: 0.5rem;
            overflow-y: auto;
            flex: 1;
            max-height: 380px;
            scrollbar-width: thin;
            scrollbar-color: var(--border-color) transparent;
        }
        .precedents-list::-webkit-scrollbar { width: 5px; }
        .precedents-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

        .precedent-item {
            padding: 0.85rem;
            border-radius: 8px;
            border: 1px solid transparent;
            margin-bottom: 6px;
            background: rgba(24, 34, 52, 0.5);
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .precedent-item:hover {
            background: rgba(30, 41, 59, 0.9);
            border-color: var(--accent-cyan);
            transform: translateX(2px);
        }
        .precedent-item.active-item {
            background: rgba(2, 132, 199, 0.2);
            border-color: var(--accent-cyan);
        }
        .precedent-item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 5px;
        }
        .status-tag {
            display: inline-block;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.68rem;
            font-weight: 800;
            letter-spacing: 0.5px;
        }
        .status-Permitted { background: #065F46; color: #34D399; border: 1px solid rgba(52, 211, 153, 0.3); }
        .status-Conditions { background: #78350F; color: #FBBF24; border: 1px solid rgba(251, 191, 36, 0.3); }
        .status-Rejected { background: #7F1D1D; color: #FCA5A5; border: 1px solid rgba(252, 165, 165, 0.3); }
        .status-Undecided, .status-Withdrawn { background: #374151; color: #D1D5DB; }

        .precedent-time { font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono); }
        .precedent-title { font-size: 0.85rem; font-weight: 700; color: #F1F5F9; line-height: 1.3; }
        .precedent-desc {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 4px;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .precedent-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 8px;
            padding-top: 6px;
            border-top: 1px solid rgba(51, 65, 85, 0.5);
        }
        .flyto-btn {
            background: transparent;
            border: none;
            color: var(--accent-cyan);
            font-size: 0.72rem;
            font-weight: 700;
            cursor: pointer;
            padding: 2px 4px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .flyto-btn:hover { text-decoration: underline; color: #7DD3FC; }
        .portal-link {
            color: #94A3B8;
            font-size: 0.72rem;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .portal-link:hover { color: var(--accent-cyan); }

        /* Custom Mapbox Glowing Markers */
        .mapbox-marker-wrap {
            position: relative;
            width: 26px;
            height: 26px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transform: translate(-50%, -50%);
        }
        .mapbox-marker-pulse {
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            opacity: 0.55;
            animation: pulse-ring 2.2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
        }
        .mapbox-marker-dot {
            width: 15px;
            height: 15px;
            border-radius: 50%;
            border: 2px solid #FFFFFF;
            box-shadow: 0 0 12px rgba(0, 0, 0, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 8px;
            font-weight: 800;
            color: #FFFFFF;
            z-index: 2;
            transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .mapbox-marker-wrap:hover .mapbox-marker-dot {
            transform: scale(1.45);
        }
        .marker-permitted .mapbox-marker-dot { background: var(--accent-green); }
        .marker-permitted .mapbox-marker-pulse { background: rgba(16, 185, 129, 0.5); }
        .marker-rejected .mapbox-marker-dot { background: var(--accent-red); }
        .marker-rejected .mapbox-marker-pulse { background: rgba(239, 68, 68, 0.5); }
        .marker-other .mapbox-marker-dot { background: var(--accent-amber); }
        .marker-other .mapbox-marker-pulse { background: rgba(245, 158, 11, 0.5); }

        @keyframes pulse-ring {
            0% { transform: scale(0.65); opacity: 0.9; }
            70% { transform: scale(2.0); opacity: 0; }
            100% { transform: scale(2.0); opacity: 0; }
        }

        /* Mapbox Popup Styling */
        .mapboxgl-popup-content {
            background: rgba(15, 23, 42, 0.95) !important;
            backdrop-filter: blur(14px) !important;
            border: 1px solid var(--border-highlight) !important;
            border-radius: 12px !important;
            padding: 14px 16px !important;
            box-shadow: 0 20px 30px rgba(0, 0, 0, 0.7) !important;
            color: var(--text-primary) !important;
            font-family: var(--font-sans) !important;
        }
        .mapboxgl-popup-anchor-top .mapboxgl-popup-tip { border-bottom-color: rgba(15, 23, 42, 0.95) !important; }
        .mapboxgl-popup-anchor-bottom .mapboxgl-popup-tip { border-top-color: rgba(15, 23, 42, 0.95) !important; }
        .mapboxgl-popup-anchor-left .mapboxgl-popup-tip { border-right-color: rgba(15, 23, 42, 0.95) !important; }
        .mapboxgl-popup-anchor-right .mapboxgl-popup-tip { border-left-color: rgba(15, 23, 42, 0.95) !important; }
        .mapboxgl-popup-close-button {
            color: var(--text-secondary) !important;
            font-size: 1.2rem !important;
            padding: 6px 10px !important;
            top: 6px !important;
            right: 6px !important;
        }
        .mapboxgl-popup-close-button:hover { color: #FFFFFF !important; background: transparent !important; }

        .popup-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .popup-ref { font-size: 0.9rem; font-weight: 700; color: #FFFFFF; margin-bottom: 3px; }
        .popup-meta { font-size: 0.74rem; color: var(--accent-cyan); margin-bottom: 6px; font-weight: 600; }
        .popup-desc { font-size: 0.78rem; color: #CBD5E1; line-height: 1.4; max-height: 90px; overflow-y: auto; margin-bottom: 10px; }
        .popup-portal-btn {
            display: inline-block;
            background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%);
            color: white;
            text-decoration: none;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 6px;
            text-align: center;
            width: 100%;
            transition: background 0.2s;
        }
        .popup-portal-btn:hover { background: #0284C7; }

        /* Mapbox Token Modal */
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        .modal-card {
            background: #111827;
            border: 1px solid var(--border-highlight);
            border-radius: 16px;
            width: 520px;
            max-width: 90vw;
            padding: 1.75rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
        }
        .modal-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 1rem;
        }
        .modal-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #0284C7 0%, #38BDF8 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        .modal-header h3 { font-size: 1.2rem; font-weight: 800; color: #FFFFFF; }
        .modal-header p { font-size: 0.8rem; color: var(--text-secondary); margin-top: 2px; }
        .modal-body p { font-size: 0.85rem; color: #CBD5E1; line-height: 1.5; margin-bottom: 1rem; }
        .modal-helper {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 0.75rem;
            font-size: 0.78rem;
            color: var(--text-secondary);
            margin-bottom: 1.25rem;
            line-height: 1.4;
        }
        .modal-helper a { color: var(--accent-cyan); text-decoration: underline; font-weight: 600; }
        .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
        .btn-secondary {
            background: #1E293B;
            border: 1px solid #334155;
            color: var(--text-secondary);
            padding: 0.7rem 1.2rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.88rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-secondary:hover { color: #FFFFFF; background: #334155; }

        /* Toast notification */
        #toast {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: #1E293B;
            border: 1px solid var(--border-color);
            color: #FFFFFF;
            padding: 10px 18px;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 600;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            z-index: 2000;
            transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #toast.show { transform: translateX(-50%) translateY(0); }
        #toast.error { border-color: var(--accent-red); color: #FCA5A5; }
        #toast.success { border-color: var(--accent-green); color: #A7F3D0; }
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <div class="logo">
                <div class="logo-icon">🏛️</div>
                PlanPulse London
            </div>
            <span class="badge">Mapbox GL JS 3D Engine</span>
        </div>
        <div class="header-right">
            <div class="stat-pill">
                <span>Database:</span>
                <span class="stat-count">181,929</span>
                <span>London Applications</span>
            </div>
            <button class="token-badge-btn" id="token-badge" onclick="openTokenModal()">
                <span class="status-dot"></span>
                <span id="token-badge-text">🔑 Mapbox Key</span>
            </button>
        </div>
    </header>

    <div class="container">
        <!-- Sidebar Controls -->
        <div class="sidebar">
            <div class="card">
                <div class="card-header">
                    <h3>📍 Property & Project Inputs</h3>
                </div>
                <div class="form-group">
                    <label for="borough-select">London Council / Borough</label>
                    <select id="borough-select" onchange="onBoroughChanged()">
                        <option value="Croydon">Croydon (26.5% Rejection Rate)</option>
                        <option value="Barnet">Barnet (18.0% Rejection Rate)</option>
                        <option value="Ealing">Ealing (13.0% Rejection Rate)</option>
                        <option value="Brent">Brent (24.9% Rejection Rate)</option>
                        <option value="Kingston">Kingston (25.4% Rejection Rate)</option>
                        <option value="Wandsworth">Wandsworth (8.5% Rejection Rate)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="size-select">Application Scale</label>
                    <select id="size-select">
                        <option value="Small">Small (Lofts, Extensions, Conversions)</option>
                        <option value="Medium">Medium (Low-rise, Infill Blocks, 4-10 units)</option>
                        <option value="Large">Large (Major Developments, 10+ units)</option>
                        <option value="All">All Scale Categories</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="keyword-input">Proposal Keyword / Scheme</label>
                    <input type="text" id="keyword-input" placeholder="e.g. extension, loft, hmo, solar, flat" value="extension">
                    <div class="kw-chips">
                        <span class="kw-chip" onclick="setKeyword('extension')">Extension</span>
                        <span class="kw-chip" onclick="setKeyword('loft')">Loft</span>
                        <span class="kw-chip" onclick="setKeyword('basement')">Basement</span>
                        <span class="kw-chip" onclick="setKeyword('conversion')">Conversion</span>
                        <span class="kw-chip" onclick="setKeyword('hmo')">HMO</span>
                        <span class="kw-chip" onclick="setKeyword('solar')">Solar</span>
                    </div>
                </div>
                <div class="form-group">
                    <label for="radius-select">Precedent Search Radius</label>
                    <select id="radius-select">
                        <option value="1.5">1.5 km (Hyper-local Street & Block)</option>
                        <option value="3.0" selected>3.0 km (Neighborhood Vicinity)</option>
                        <option value="5.0">5.0 km (Full Borough Sector)</option>
                    </select>
                </div>
                <button class="btn-primary" onclick="runAnalysis()">⚡ Calculate Risk & Render 3D Precedents</button>
            </div>

            <!-- AI Risk Prediction Card -->
            <div class="card" id="risk-card">
                <div class="card-header">
                    <h3>📊 AI Risk Prediction</h3>
                    <div class="risk-badge" id="risk-badge" style="background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.3);">CALCULATING</div>
                </div>
                <div class="metric-row">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase;">Approval Probability</div>
                        <div class="metric-val" id="prob-val" style="color: var(--accent-green);">--%</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase;">Rejection Risk</div>
                        <div class="metric-val" id="risk-val" style="color: var(--accent-red); font-size: 1.5rem;">--%</div>
                    </div>
                </div>
                <div class="metric-subgrid">
                    <div class="metric-mini-box">
                        <div class="mini-label">Estimated ETA</div>
                        <div class="mini-val" id="eta-val">-- days</div>
                    </div>
                    <div class="metric-mini-box">
                        <div class="mini-label">Sample Data</div>
                        <div class="mini-val" id="sample-val">-- rows</div>
                    </div>
                </div>
            </div>

            <!-- Borough Rejection Rates Bar Chart -->
            <div class="card">
                <div class="card-header">
                    <h3>📈 Council Rejection Benchmarks</h3>
                </div>
                <canvas id="boroughChart" height="190"></canvas>
            </div>
        </div>

        <!-- Mapbox Rendering Container -->
        <div id="map-container">
            <div id="map"></div>

            <!-- Mapbox Style Switcher Floating Bar -->
            <div class="map-style-bar">
                <button class="style-btn active" data-style="mapbox://styles/mapbox/dark-v11" onclick="switchMapStyle(this)">🌙 Dark 3D</button>
                <button class="style-btn" data-style="mapbox://styles/mapbox/navigation-night-v1" onclick="switchMapStyle(this)">🌃 Night Glow</button>
                <button class="style-btn" data-style="mapbox://styles/mapbox/satellite-streets-v12" onclick="switchMapStyle(this)">🛰️ Satellite</button>
                <button class="style-btn" data-style="mapbox://styles/mapbox/streets-v12" onclick="switchMapStyle(this)">🗺️ Streets</button>
            </div>

            <!-- Map Tools Bar -->
            <div class="map-tools-bar">
                <button id="toggle-3d-btn" class="tool-btn active" onclick="toggle3DBuildings()">🏢 3D Buildings: ON</button>
                <button class="tool-btn" onclick="resetLondonView()">🇬🇧 London Wide</button>
            </div>

            <!-- Precedents Drawer Panel -->
            <div class="results-panel">
                <div class="panel-header">
                    <h4>🔎 Spatial Precedents <span class="panel-count" id="prec-count">0</span></h4>
                    <span style="font-size: 0.72rem; color: var(--text-muted);">Click to 3D Fly-To</span>
                </div>
                <div class="precedents-list" id="precedents-list">
                    <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                        Click "Calculate Risk & Render 3D Precedents" to load spatial application history.
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Mapbox Access Token Setup Modal -->
    <div id="mapbox-token-modal" class="modal-overlay" style="display: none;">
        <div class="modal-card">
            <div class="modal-header">
                <div class="modal-icon">🗺️</div>
                <div>
                    <h3>Mapbox Access Token</h3>
                    <p>WebGL Vector Map & 3D Building Extrusions</p>
                </div>
            </div>
            <div class="modal-body">
                <p>PlanPulse London uses Mapbox GL JS v3 for hardware-accelerated 60 FPS vector map rendering, satellite imagery, and photorealistic 3D building extrusions across Greater London.</p>
                <div class="form-group">
                    <label for="modal-token-input">Mapbox Public Token (starts with <code>pk.</code>)</label>
                    <input type="text" id="modal-token-input" placeholder="pk.eyJ1..." autocomplete="off" spellcheck="false" />
                </div>
                <div class="modal-helper">
                    💡 <b>No token?</b> Get a free personal Mapbox public token in 30 seconds at <a href="https://account.mapbox.com/access-tokens/" target="_blank" rel="noopener noreferrer">mapbox.com ↗</a> (includes 50,000 free map views each month).<br>
                    You can also define <code>MAPBOX_ACCESS_TOKEN</code> in your terminal or <code>.env</code> file.
                </div>
                <div class="modal-actions">
                    <button class="btn-secondary" onclick="closeTokenModal()">Cancel</button>
                    <button class="btn-primary" style="width: auto; padding: 0.7rem 1.4rem;" onclick="saveMapboxToken()">🚀 Launch Mapbox Engine</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast"></div>

    <script>
        // Server injected token if set in environment
        window.MAPBOX_ENV_TOKEN = "__MAPBOX_ENV_TOKEN__";

        let map = null;
        let mapReady = false;
        let currentMapStyle = 'mapbox://styles/mapbox/dark-v11';
        let buildings3DEnabled = true;
        let chartInstance = null;
        let boroughDataMap = {};
        let currentPrecedents = [];
        let markerRegistry = [];

        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/[&<>"']/g, function(m) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
            });
        }

        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = `show ${type}`;
            setTimeout(() => { toast.className = ''; }, 4500);
        }

        function getActiveToken() {
            const envTok = (window.MAPBOX_ENV_TOKEN && !window.MAPBOX_ENV_TOKEN.includes('__MAPBOX_ENV_TOKEN__')) ? window.MAPBOX_ENV_TOKEN.trim() : '';
            const storedTok = (localStorage.getItem('planpulse_mapbox_token') || '').trim();
            return envTok || storedTok;
        }

        function updateTokenBadge() {
            const token = getActiveToken();
            const badge = document.getElementById('token-badge');
            const badgeText = document.getElementById('token-badge-text');
            if (token) {
                badge.className = 'token-badge-btn connected';
                badgeText.textContent = '🔑 Mapbox Active';
            } else {
                badge.className = 'token-badge-btn disconnected';
                badgeText.textContent = '⚠️ Connect Mapbox';
            }
        }

        function openTokenModal() {
            const modal = document.getElementById('mapbox-token-modal');
            const input = document.getElementById('modal-token-input');
            input.value = getActiveToken();
            modal.style.display = 'flex';
        }

        function closeTokenModal() {
            document.getElementById('mapbox-token-modal').style.display = 'none';
        }

        function saveMapboxToken() {
            const input = document.getElementById('modal-token-input');
            const val = (input.value || '').trim();
            if (!val || !val.startsWith('pk.')) {
                alert('Please enter a valid Mapbox public token starting with "pk."');
                return;
            }
            localStorage.setItem('planpulse_mapbox_token', val);
            closeTokenModal();
            showToast('Mapbox token saved! Initializing WebGL engine...', 'success');
            updateTokenBadge();
            initMapbox();
        }

        function add3DBuildingsLayer(targetMap) {
            if (!targetMap) return;
            try {
                const layers = targetMap.getStyle()?.layers;
                if (!layers) return;
                const labelLayerId = layers.find(
                    (layer) => layer.type === 'symbol' && layer.layout && layer.layout['text-field']
                )?.id;

                if (!targetMap.getLayer('3d-buildings')) {
                    targetMap.addLayer(
                        {
                            'id': '3d-buildings',
                            'source': 'composite',
                            'source-layer': 'building',
                            'filter': ['==', 'extrude', 'true'],
                            'type': 'fill-extrusion',
                            'minzoom': 13,
                            'paint': {
                                'fill-extrusion-color': [
                                    'interpolate',
                                    ['linear'],
                                    ['get', 'height'],
                                    0, '#131D2D',
                                    30, '#1E2D44',
                                    70, '#2B3F5E',
                                    150, '#3E5982'
                                ],
                                'fill-extrusion-height': [
                                    'interpolate',
                                    ['linear'],
                                    ['zoom'],
                                    13, 0,
                                    15.05, ['get', 'height']
                                ],
                                'fill-extrusion-base': [
                                    'interpolate',
                                    ['linear'],
                                    ['zoom'],
                                    13, 0,
                                    15.05, ['get', 'min_height']
                                ],
                                'fill-extrusion-opacity': 0.85
                            }
                        },
                        labelLayerId
                    );
                }
            } catch (err) {
                console.warn('3D building layer note:', err);
            }
        }

        function switchMapStyle(btn) {
            if (!map) {
                openTokenModal();
                return;
            }
            document.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const styleUri = btn.getAttribute('data-style');
            currentMapStyle = styleUri;
            map.setStyle(styleUri);
            map.once('style.load', () => {
                if (buildings3DEnabled) add3DBuildingsLayer(map);
                reAddMarkersToMap();
            });
        }

        function toggle3DBuildings() {
            const btn = document.getElementById('toggle-3d-btn');
            buildings3DEnabled = !buildings3DEnabled;
            if (buildings3DEnabled) {
                btn.className = 'tool-btn active';
                btn.textContent = '🏢 3D Buildings: ON';
                if (map) add3DBuildingsLayer(map);
            } else {
                btn.className = 'tool-btn';
                btn.textContent = '🏢 3D Buildings: OFF';
                if (map && map.getLayer('3d-buildings')) {
                    map.removeLayer('3d-buildings');
                }
            }
        }

        function resetLondonView() {
            if (!map) return;
            map.flyTo({
                center: [-0.1278, 51.5074],
                zoom: 11,
                pitch: 35,
                bearing: -10,
                speed: 1.2
            });
        }

        function initMapbox() {
            const token = getActiveToken();
            updateTokenBadge();

            if (!token) {
                openTokenModal();
                return;
            }

            try {
                if (map) {
                    map.remove();
                    map = null;
                }

                mapboxgl.accessToken = token;
                map = new mapboxgl.Map({
                    container: 'map',
                    style: currentMapStyle,
                    center: [-0.0962, 51.3660], // Default center on Croydon
                    zoom: 13,
                    pitch: 50,
                    bearing: -15,
                    antialias: true
                });

                map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-right');
                map.addControl(new mapboxgl.FullscreenControl(), 'top-right');
                map.addControl(new mapboxgl.ScaleControl({ unit: 'metric' }), 'bottom-left');

                map.on('style.load', () => {
                    if (buildings3DEnabled) add3DBuildingsLayer(map);
                });

                map.on('load', () => {
                    mapReady = true;
                    runAnalysis();
                });

                map.on('error', (e) => {
                    console.error('Mapbox error event:', e);
                    if (e.error && (e.error.status === 401 || e.error.status === 403 || String(e.error).includes('401') || String(e.error).includes('403'))) {
                        showToast('Mapbox Token Authentication failed. Please check your token.', 'error');
                        document.getElementById('token-badge').className = 'token-badge-btn disconnected';
                        document.getElementById('token-badge-text').textContent = '⚠️ Token Invalid';
                    }
                });

            } catch (err) {
                console.error('Failed to init Mapbox:', err);
                showToast('Mapbox initialization error: ' + err.message, 'error');
                openTokenModal();
            }
        }

        async function loadBoroughBenchmarks() {
            try {
                const res = await fetch('/api/boroughs');
                const data = await res.json();
                
                // Populate borough selector
                const select = document.getElementById('borough-select');
                select.innerHTML = '';
                boroughDataMap = {};

                data.forEach((b, index) => {
                    boroughDataMap[b.borough] = b;
                    const opt = document.createElement('option');
                    opt.value = b.borough;
                    opt.textContent = `${b.borough} (${b.rejection_rate}% Rejection, ${b.total.toLocaleString()} apps)`;
                    if (b.borough === 'Croydon') opt.selected = true;
                    select.appendChild(opt);
                });

                // Top 6 rejected boroughs for chart
                const sortedByRejection = [...data].sort((a, b) => b.rejection_rate - a.rejection_rate).slice(0, 6);
                const ctx = document.getElementById('boroughChart').getContext('2d');
                if (chartInstance) chartInstance.destroy();
                chartInstance = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: sortedByRejection.map(b => b.borough),
                        datasets: [{
                            label: 'Rejection %',
                            data: sortedByRejection.map(b => b.rejection_rate),
                            backgroundColor: '#EF4444',
                            borderRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(ctx) { return `Rejection Rate: ${ctx.raw}%`; }
                                }
                            }
                        },
                        scales: {
                            y: {
                                ticks: { color: '#94A3B8', callback: v => v + '%' },
                                grid: { color: 'rgba(51, 65, 85, 0.4)' }
                            },
                            x: {
                                ticks: { color: '#94A3B8', font: { size: 10 } },
                                grid: { display: false }
                            }
                        }
                    }
                });
            } catch (err) {
                console.error('Failed to fetch borough benchmarks:', err);
            }
        }

        function setKeyword(kw) {
            document.getElementById('keyword-input').value = kw;
            runAnalysis();
        }

        function onBoroughChanged() {
            runAnalysis();
        }

        function reAddMarkersToMap() {
            if (!map || !currentPrecedents.length) return;
            renderPrecedents(currentPrecedents);
        }

        function renderPrecedents(precedents) {
            currentPrecedents = precedents;
            // Clean up existing markers
            markerRegistry.forEach(m => m.marker.remove());
            markerRegistry = [];

            const listEl = document.getElementById('precedents-list');
            listEl.innerHTML = '';
            document.getElementById('prec-count').innerText = precedents.length;

            if (!precedents || precedents.length === 0) {
                listEl.innerHTML = '<div style="padding: 1.5rem; color: var(--text-muted); text-align: center; font-size: 0.85rem;">No spatial precedents found matching criteria within this radius. Try widening search radius or relaxing keyword.</div>';
                return;
            }

            precedents.forEach((p, idx) => {
                const statusClass = p.status === 'Permitted' ? 'marker-permitted' : (p.status === 'Rejected' ? 'marker-rejected' : 'marker-other');
                const statusTagClass = 'status-' + (p.status || 'Undecided');

                let marker = null;
                if (map && p.lat && p.lng) {
                    const el = document.createElement('div');
                    el.className = `mapbox-marker-wrap ${statusClass}`;
                    el.innerHTML = `
                        <div class="mapbox-marker-pulse"></div>
                        <div class="mapbox-marker-dot">${p.status === 'Permitted' ? '✓' : (p.status === 'Rejected' ? '✕' : '•')}</div>
                    `;

                    const popupHtml = `
                        <div class="popup-top">
                            <span class="status-tag ${statusTagClass}">${p.status ? p.status.toUpperCase() : 'UNKNOWN'}</span>
                            <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">${p.days_to_decision ? p.days_to_decision + ' days' : ''}</span>
                        </div>
                        <div class="popup-ref">${escapeHtml(p.name)}</div>
                        <div class="popup-meta">🏛️ ${escapeHtml(p.area_name || '')} &bull; ${escapeHtml(p.app_size || '')} Scale</div>
                        <div class="popup-desc">${escapeHtml(p.description || 'No description provided')}</div>
                        ${p.url ? `<a href="${p.url}" target="_blank" rel="noopener noreferrer" class="popup-portal-btn">View Council Planning Portal ↗</a>` : ''}
                    `;

                    const popup = new mapboxgl.Popup({
                        offset: 22,
                        closeButton: true,
                        closeOnClick: false,
                        maxWidth: '320px'
                    }).setHTML(popupHtml);

                    marker = new mapboxgl.Marker({ element: el, anchor: 'center' })
                        .setLngLat([p.lng, p.lat])
                        .setPopup(popup)
                        .addTo(map);

                    markerRegistry.push({ id: idx, marker: marker, data: p });
                }

                const item = document.createElement('div');
                item.className = 'precedent-item';
                item.id = `prec-item-${idx}`;
                item.onclick = () => focusPrecedent(idx);
                item.innerHTML = `
                    <div class="precedent-item-header">
                        <span class="status-tag ${statusTagClass}">${(p.status || 'OTHER').toUpperCase()}</span>
                        <span class="precedent-time">${p.days_to_decision ? p.days_to_decision + ' days to decision' : ''}</span>
                    </div>
                    <div class="precedent-title">${escapeHtml(p.name)} <span style="font-weight: 500; color: var(--text-muted);">(${escapeHtml(p.area_name || '')})</span></div>
                    <div class="precedent-desc">${escapeHtml(p.description || 'No description available')}</div>
                    <div class="precedent-footer">
                        <button class="flyto-btn" onclick="event.stopPropagation(); focusPrecedent(${idx})">📍 Fly to 3D Site</button>
                        ${p.url ? `<a href="${p.url}" target="_blank" rel="noopener noreferrer" class="portal-link" onclick="event.stopPropagation()">Council Portal ↗</a>` : ''}
                    </div>
                `;
                listEl.appendChild(item);
            });
        }

        function focusPrecedent(index) {
            const found = markerRegistry.find(m => m.id === index);
            if (!found || !map) return;

            // Highlight list item
            document.querySelectorAll('.precedent-item').forEach(el => el.classList.remove('active-item'));
            const itemEl = document.getElementById(`prec-item-${index}`);
            if (itemEl) {
                itemEl.classList.add('active-item');
                itemEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }

            // Smooth high-pitch fly-to in Mapbox
            map.flyTo({
                center: [found.data.lng, found.data.lat],
                zoom: 16.5,
                pitch: 60,
                bearing: -20,
                speed: 1.3,
                curve: 1.4,
                essential: true
            });

            // Toggle target popup
            markerRegistry.forEach(m => {
                if (m.marker.getPopup() && m.marker.getPopup().isOpen()) {
                    m.marker.togglePopup();
                }
            });
            found.marker.togglePopup();
        }

        async function runAnalysis() {
            const b = document.getElementById('borough-select').value;
            const sz = document.getElementById('size-select').value;
            const kw = document.getElementById('keyword-input').value;
            const rad = document.getElementById('radius-select').value;

            // 1. Fetch AI Risk Prediction
            try {
                const riskRes = await fetch(`/api/predict?borough=${encodeURIComponent(b)}&app_size=${encodeURIComponent(sz)}&keyword=${encodeURIComponent(kw)}`);
                const risk = await riskRes.json();

                const probValEl = document.getElementById('prob-val');
                probValEl.innerText = risk.approval_probability + '%';
                probValEl.style.color = risk.risk_color;

                const riskValEl = document.getElementById('risk-val');
                riskValEl.innerText = risk.rejection_risk + '%';
                riskValEl.style.color = risk.risk_color;

                const badgeEl = document.getElementById('risk-badge');
                badgeEl.innerText = risk.risk_level;
                badgeEl.style.color = risk.risk_color;
                badgeEl.style.borderColor = risk.risk_color;
                badgeEl.style.background = risk.risk_color + '22';

                document.getElementById('eta-val').innerText = risk.estimated_days + ' days';
                document.getElementById('sample-val').innerText = risk.sample_size.toLocaleString() + ' records';
            } catch (err) {
                console.error('Failed to predict risk:', err);
            }

            // 2. Determine Coordinates for Borough Centroid
            let coords = [-0.0962, 51.3660]; // default Croydon [lng, lat]
            if (boroughDataMap[b] && boroughDataMap[b].lat && boroughDataMap[b].lng) {
                coords = [boroughDataMap[b].lng, boroughDataMap[b].lat];
            } else {
                const fallbackCoords = {
                    'Croydon': [-0.0982, 51.3762],
                    'Barnet': [-0.2000, 51.6252],
                    'Ealing': [-0.3089, 51.5130],
                    'Brent': [-0.2817, 51.5588],
                    'Kingston': [-0.3064, 51.4085],
                    'Wandsworth': [-0.1910, 51.4567]
                };
                if (fallbackCoords[b]) coords = fallbackCoords[b];
            }

            // 3. Smooth Camera Fly-To in Mapbox
            if (map && mapReady) {
                map.flyTo({
                    center: coords,
                    zoom: 13.5,
                    pitch: 52,
                    bearing: -15,
                    speed: 1.2,
                    curve: 1.4,
                    essential: true
                });
            }

            // 4. Fetch Spatial Precedents
            try {
                const precRes = await fetch(`/api/precedents?lat=${coords[1]}&lng=${coords[0]}&keyword=${encodeURIComponent(kw)}&radius=${rad}&limit=30`);
                const precedents = await precRes.json();
                renderPrecedents(precedents);
            } catch (err) {
                console.error('Failed to fetch precedents:', err);
                showToast('Failed to load spatial precedents: ' + err.message, 'error');
            }
        }

        // Initialize application
        window.addEventListener('DOMContentLoaded', async () => {
            await loadBoroughBenchmarks();
            initMapbox();
        });
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Please run convert_db.py first.")
    else:
        # Re-use port address if restarted
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("", PORT), PlanPulseHandler)
        print(f"🚀 PlanPulse Mapbox 3D Server is live at http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
