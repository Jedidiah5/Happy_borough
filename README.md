# 🏛️ PlanPulse London — AI Planning Risk & Precedent Engine

> **Data-driven planning permission intelligence, risk scoring, and 3D precedent exploration across 181,929 Greater London housing applications (2022–2025).**

![PlanPulse London](https://img.shields.io/badge/Platform-Greater%20London-0284C7?style=flat-square)
![Dataset](https://img.shields.io/badge/Database-181%2C929%20Applications-10B981?style=flat-square)
![Map Engine](https://img.shields.io/badge/Map%20Engine-Mapbox%20GL%20JS%20v3-38BDF8?style=flat-square)
![MCP](https://img.shields.io/badge/AI%20Protocol-Model%20Context%20Protocol%20(MCP)-F59E0B?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-slate?style=flat-square)

---

## 📌 Overview

**PlanPulse London** is an AI-powered planning feasibility and spatial analytics platform built on over 181,000 historical planning applications submitted to London borough councils between 2022 and 2025.

Whether you are evaluating a loft conversion, a residential extension, an HMO conversion, or a multi-unit infill scheme, PlanPulse evaluates council precedent, quantifies rejection risk, estimates decision timelines, and renders high-density historical applications directly in photorealistic 3D.

---

## ✨ Key Features

### 🗺️ Mapbox GL JS v3 3D Spatial Rendering
- **Hardware-Accelerated WebGL**: Fluid 60 FPS vector map rendering across all 35 London local planning authorities.
- **3D Building Extrusions**: London's architectural skyline rendered in realistic 3D (`fill-extrusion`) with height-based gradient shading and pitch control.
- **Dynamic Style Switcher**: Seamless toggle between **Dark 3D**, **Night Glow**, **Satellite Imagery**, and **Streets**.
- **Glowing Status Markers**: Custom pulsating DOM markers color-coded by application outcome:
  - 🟢 **Permitted** (`#10B981`)
  - 🔴 **Rejected** (`#EF4444`)
  - 🟡 **Conditions / Withdrawn** (`#F59E0B`)
- **Glassmorphic Precedent Cards**: Interactive popups with council references, proposal summaries, ETA to decision, and one-click deep links to official council planning portals.
- **Interactive 3D Fly-To**: Clicking any precedent smoothly animates the camera to the property site at a 60° perspective angle.

### 📊 AI Planning Risk & Decision ETA Modeling
- **Approval & Rejection Probability**: Computes predictive risk scores based on historical borough precedent, proposal scale, and keyword semantics.
- **Decision Timelines (ETA)**: Calculates real-world council turnaround times in calendar days.
- **Granular Filter Matrix**:
  - **Borough**: All 35 London councils (Croydon, Barnet, Ealing, Wandsworth, Brent, Westminster, etc.).
  - **Scale**: Small (lofts/extensions), Medium (infill/low-rise), Large (major developments 10+ units).
  - **Keywords**: Instant chips for `extension`, `loft`, `basement`, `conversion`, `hmo`, `solar`.
  - **Spatial Radius**: Hyper-local (1.5 km), Neighborhood (3.0 km), or Sector (5.0 km).

### 📈 Council Rejection Benchmarks
- Real-time comparison of approval and refusal rates across London councils.
- Identifies strict planning jurisdictions (e.g. Croydon at 26.5% refusal, Kingston at 25.4%, Brent at 24.9%) versus pro-development authorities (e.g. Wandsworth at 8.5%).

### 🤖 Model Context Protocol (MCP) Server
- Exposes tools via standard JSON-RPC for AI assistants (Antigravity, Claude Desktop, Cursor):
  - `get_borough_stats`: Retrieve aggregated application metrics for any borough.
  - `search_precedents`: Find spatial precedents matching keyword and radius.
  - `predict_risk`: Predict approval likelihood and estimated days.

### 😊 HappyBorough London Index (`happiness_server.py`)
- Multi-factor neighborhood livability fusion prototype integrating:
  - **ONS Well-being Survey** benchmarks
  - **UK Police Open Data** crime & safety indices
  - **TfL PTAL** public transport accessibility ratings
  - **Council Planning** volume & approval rates

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Details |
|---|---|---|
| **Frontend** | Vanilla JS, HTML5, Modern CSS | Dark glassmorphism, responsive grid, micro-animations |
| **Map Engine** | Mapbox GL JS v3.2.0 | 3D vector extrusions, custom glowing markers, camera fly-to |
| **Data Visualization** | Chart.js 4.x | Rejection rate benchmarks & analytics |
| **Typography** | Google Fonts | *Plus Jakarta Sans* (UI) & *JetBrains Mono* (metrics) |
| **Backend** | Python 3 (`http.server`, `socketserver`) | Lightweight, zero external web framework dependencies |
| **Database** | SQLite 3 (`housing.db`) | 118 MB indexed database with spatial delta bounding queries |
| **AI Protocol** | MCP (`mcp_server.py`) | Model Context Protocol tools for AI agent integration |

---

## 📁 Repository Structure

```
NewSpeak/
├── server.py               # Main PlanPulse Mapbox 3D application & REST API server (Port 8080)
├── mcp_server.py           # Model Context Protocol (MCP) server for AI assistants
├── happiness_server.py     # HappyBorough neighborhood vibe & livability server (Port 8085)
├── convert_db.py           # Database build & index script (CSV -> SQLite)
├── housing.db              # 118MB indexed SQLite database (181,929 records)
├── .env.example            # Environment configuration template
└── README.md               # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.9+** (no virtualenv or pip packages required for the core server!)
- A free **Mapbox Public Access Token** ([get one here](https://account.mapbox.com/access-tokens/))

### 2. Configure Mapbox Token *(Optional)*
You can either set the token in your environment or enter it directly in the in-app setup modal:

```bash
cp .env.example .env
# Edit .env and paste your Mapbox public token:
# MAPBOX_ACCESS_TOKEN=pk.eyJ1...
```

Alternatively, export it in your shell:
```bash
export MAPBOX_ACCESS_TOKEN="pk.your_token_here"
```

### 3. Launch PlanPulse London

```bash
python3 server.py
```

Open your browser to:
👉 **http://localhost:8080**

*(If no token was provided in `.env`, a friendly setup prompt will appear where you can paste your token directly into the UI—it is saved in `localStorage` for future sessions).*

---

## 🔌 Model Context Protocol (MCP) Setup

To connect PlanPulse directly into **Claude Desktop**, **Antigravity**, or **Cursor**, add the following to your MCP configuration file:

```json
{
  "mcpServers": {
    "planpulse": {
      "command": "python3",
      "args": [
        "/Users/nashyosh/Desktop/Personal Project/NewSpeak/mcp_server.py"
      ]
    }
  }
}
```

### Available MCP Tools:
1. `get_borough_stats(borough_name)`: Returns total applications, approvals, refusals, rejection rate %, and average decision days.
2. `search_precedents(lat, lng, keyword, radius_km, limit)`: Returns nearest historical applications with full planning portal links and outcomes.
3. `predict_risk(borough, app_size, keyword)`: Returns approval probability percentage, rejection risk, and sample size.

---

## 📡 REST API Reference

The core server (`server.py`) provides fast JSON endpoints:

### 1. Borough Benchmarks
```http
GET /api/boroughs
```
**Response:**
```json
[
  {
    "borough": "Croydon",
    "total": 9914,
    "permitted": 6895,
    "rejected": 2630,
    "rejection_rate": 26.5,
    "approval_rate": 69.5,
    "avg_days": 83.6,
    "dwellings": 61783,
    "lat": 51.366,
    "lng": -0.0962
  }
]
```

### 2. AI Risk Prediction
```http
GET /api/predict?borough=Croydon&app_size=Small&keyword=extension
```
**Response:**
```json
{
  "borough": "Croydon",
  "app_size": "Small",
  "keyword": "extension",
  "sample_size": 5823,
  "approval_probability": 76.2,
  "rejection_risk": 21.2,
  "risk_level": "MEDIUM RISK",
  "risk_color": "#F59E0B",
  "estimated_days": 72.6
}
```

### 3. Spatial Precedents
```http
GET /api/precedents?lat=51.3660&lng=-0.0962&keyword=extension&radius=2.5&limit=25
```
**Response:**
```json
[
  {
    "name": "Croydon/23/00736/HSE",
    "area_name": "Croydon",
    "status": "Permitted",
    "decision": "Application Permitted",
    "days_to_decision": 54.0,
    "url": "https://publicaccess3.croydon.gov.uk/online-applications/...",
    "description": "Erection of single storey rear extension...",
    "app_size": "Small",
    "lat": 51.365252,
    "lng": -0.096522
  }
]
```

---

## 🗄️ Database Rebuilding *(Optional)*

If you ever update the source CSV dataset (`foundations_london_housing_2022_2025_*.csv`):

```bash
python3 convert_db.py
```
This parses the 181k+ records and creates the optimized indexes (`idx_borough`, `idx_lat_lng`, `idx_status`, `idx_app_size`) in ~15 seconds.

---

## 💡 Use Cases
- **Architects & Planning Consultants**: Screen proposal feasibility and council risk prior to submission.
- **Property Developers**: Identify favorable boroughs and uncover hyper-local approved precedents to support design and access statements.
- **Homeowners**: Assess realistic timelines and refusal risks for extensions, dormers, and loft conversions.
- **Civic Tech & Housing Advocates**: Track council planning velocity, housing delivery figures, and refusal patterns across London.

---

## 📄 License
This project is open-source and licensed under the [MIT License](LICENSE).
Planning application data is published under the UK Open Government Licence (OGL).
