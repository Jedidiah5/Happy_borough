import sqlite3
import json
import sys
import math

DB_PATH = 'housing.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_borough_stats(borough_name: str):
    """Retrieve aggregate statistics for a specific London borough."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT 
            COUNT(*) as total_apps,
            SUM(CASE WHEN status IN ('Permitted', 'Conditions') THEN 1 ELSE 0 END) as permitted_count,
            SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected_count,
            AVG(days_to_decision) as avg_days,
            SUM(n_dwellings) as total_dwellings
        FROM applications
        WHERE LOWER(area_name) = LOWER(?)
    ''', (borough_name,))
    row = dict(c.fetchone())
    conn.close()
    
    total = row['total_apps'] or 0
    rej = row['rejected_count'] or 0
    perm = row['permitted_count'] or 0
    
    row['rejection_rate'] = round((rej / total * 100), 2) if total > 0 else 0
    row['approval_rate'] = round((perm / total * 100), 2) if total > 0 else 0
    row['avg_days'] = round(row['avg_days'], 1) if row['avg_days'] else None
    return row

def search_precedents(lat: float, lng: float, keyword: str = "", radius_km: float = 1.0, limit: int = 10):
    """Find historical planning precedents near a lat/lng coordinate."""
    # Rough approximation: 1 deg lat ~ 111km, 1 deg lng ~ 69km in London
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / 69.0
    
    conn = get_db()
    c = conn.cursor()
    
    query = '''
        SELECT name, area_name, status, decision, days_to_decision, url, description, app_size, app_type, lat, lng,
               ((lat - ?)*(lat - ?) + (lng - ?)*(lng - ?)) as dist
        FROM applications
        WHERE lat BETWEEN ? AND ?
          AND lng BETWEEN ? AND ?
    '''
    params = [lat, lat, lng, lng, lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta]
    
    if keyword:
        query += " AND description LIKE ?"
        params.append(f"%{keyword}%")
        
    query += " ORDER BY dist ASC LIMIT ?"
    params.append(limit)
    
    c.execute(query, params)
    results = [dict(r) for r in c.fetchall()]
    conn.close()
    return results

def predict_risk(borough: str, app_size: str, keyword: str = ""):
    """Predict approval probability and decision ETA based on borough, app size, and proposal keyword."""
    conn = get_db()
    c = conn.cursor()
    
    query = '''
        SELECT status, days_to_decision, n_dwellings
        FROM applications
        WHERE LOWER(area_name) = LOWER(?)
    '''
    params = [borough]
    
    if app_size:
        query += " AND LOWER(app_size) = LOWER(?)"
        params.append(app_size)
        
    if keyword:
        query += " AND description LIKE ?"
        params.append(f"%{keyword}%")
        
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {"error": "Insufficient precedent data for specified criteria."}
        
    total = len(rows)
    permitted = sum(1 for r in rows if r['status'] in ('Permitted', 'Conditions'))
    rejected = sum(1 for r in rows if r['status'] == 'Rejected')
    days_list = [r['days_to_decision'] for r in rows if r['days_to_decision'] is not None and 0 <= r['days_to_decision'] <= 365]
    
    approval_prob = round((permitted / total * 100), 1) if total > 0 else 0.0
    rejection_risk = round((rejected / total * 100), 1) if total > 0 else 0.0
    avg_days = round(sum(days_list) / len(days_list), 1) if days_list else 56.0
    
    # Risk Level classification
    if approval_prob >= 80:
        risk_level = "LOW RISK"
    elif approval_prob >= 65:
        risk_level = "MEDIUM RISK"
    else:
        risk_level = "HIGH RISK"

    return {
        "borough": borough,
        "app_size": app_size,
        "keyword": keyword,
        "sample_size": total,
        "approval_probability": approval_prob,
        "rejection_risk": rejection_risk,
        "risk_level": risk_level,
        "estimated_days": avg_days
    }

# Standard MCP JSON-RPC Server execution handler
if __name__ == "__main__":
    print("PlanPulse MCP Server is active.")
    # Example quick test
    print("Test Borough Stats (Croydon):", get_borough_stats("Croydon"))
    print("Test Risk Prediction (Croydon, Small, extension):", predict_risk("Croydon", "Small", "extension"))
