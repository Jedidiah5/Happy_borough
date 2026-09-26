import sqlite3
import csv
import time
import os

def build_database(csv_path="foundations_london_housing_2022_2025_20260810T013626Z.csv", db_path="housing.db"):
    print(f"Reading {csv_path} and creating {db_path}...")
    start = time.time()
    
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        area_name TEXT,
        reference TEXT,
        uid TEXT,
        url TEXT,
        description TEXT,
        app_type TEXT,
        app_size TEXT,
        status TEXT,
        decision TEXT,
        start_date TEXT,
        decided_date TEXT,
        days_to_decision REAL,
        n_dwellings REAL,
        housing_relevance_score REAL,
        lat REAL,
        lng REAL,
        ward_name TEXT,
        agent_company TEXT
    )
    ''')

    c.execute('CREATE INDEX idx_borough ON applications(area_name)')
    c.execute('CREATE INDEX idx_lat_lng ON applications(lat, lng)')
    c.execute('CREATE INDEX idx_status ON applications(status)')
    c.execute('CREATE INDEX idx_app_size ON applications(app_size)')

    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        to_insert = []
        for r in reader:
            try:
                lat = float(r['lat']) if r.get('lat') else None
                lng = float(r['lng']) if r.get('lng') else None
            except ValueError:
                lat, lng = None, None
                
            try:
                days = float(r['days_to_decision']) if r.get('days_to_decision') else None
            except ValueError:
                days = None
                
            try:
                dwellings = float(r['n_dwellings']) if r.get('n_dwellings') else 0.0
            except ValueError:
                dwellings = 0.0

            try:
                rel_score = float(r['housing_relevance_score']) if r.get('housing_relevance_score') else None
            except ValueError:
                rel_score = None

            to_insert.append((
                r.get('name'), r.get('area_name'), r.get('reference'), r.get('uid'),
                r.get('url'), r.get('description'), r.get('app_type'), r.get('app_size'),
                r.get('status'), r.get('decision'), r.get('start_date'), r.get('decided_date'),
                days, dwellings, rel_score, lat, lng, r.get('ward_name'), r.get('agent_company')
            ))

    c.executemany('''
    INSERT INTO applications (name, area_name, reference, uid, url, description, app_type, app_size, status, decision, start_date, decided_date, days_to_decision, n_dwellings, housing_relevance_score, lat, lng, ward_name, agent_company)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', to_insert)

    conn.commit()
    conn.close()
    print(f"Database successfully indexed {len(to_insert)} rows in {time.time() - start:.2f} seconds.")

if __name__ == "__main__":
    build_database()
