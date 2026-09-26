# 😊 HappyBorough London — Legal Neighborhood Vibe & Happiness Index

> **Multi-factor open data fusion platform for ranking London's happiest, safest, and most livable boroughs based on your personalized lifestyle priorities.**

![Platform](https://img.shields.io/badge/Platform-Greater%20London-10B981?style=flat-square)
![Data Fusion](https://img.shields.io/badge/Open%20Data-ONS%20%2B%20Police%20%2B%20TfL%20%2B%20Planning-38BDF8?style=flat-square)
![Architecture](https://img.shields.io/badge/Stack-Python%20%2B%20Leaflet%20%2B%20SQLite-0284C7?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-slate?style=flat-square)

---

## 📌 Overview

Choosing where to live or invest in London is often reduced to house prices and rent costs. **HappyBorough London** changes that by fusing official UK open data benchmarks into a personalized, interactive livability and happiness engine.

By combining well-being surveys, crime statistics, public transport accessibility, and urban green canopy density with official council planning metrics, HappyBorough enables citizens, homebuyers, and urban researchers to find the neighborhood that aligns with their personal lifestyle values.

---

## 🌟 Key Features

### 🎛️ Personalized Priority Weighting
- **Real-Time Sliders**: Adjust relative weights across the 4 key livability dimensions:
  - 🛡️ **Safety & Low Crime** (UK Police Open Data benchmarks)
  - 🌳 **Parks & Green Space** (Canopy and open parkland density)
  - 🚆 **Public Transport Accessibility** (TfL PTAL connectivity ratings)
  - 😊 **Community Satisfaction** (ONS Personal Well-being & Life Satisfaction Survey)
- **Instant Recalculation**: Live dynamic re-weighting and normalization so sliders always sum to 100%.

### 🏆 Dynamic Borough Leaderboard
- Real-time ranked list of top-matched London boroughs based on your current slider weights.
- Composite **Happiness Score (0–100)** for each borough.
- Detailed metric breakdowns: safety score, green space index, transport connectivity, and ONS life satisfaction.
- Integrated council planning approval rates and application volumes queried live from `housing.db`.

### 🗺️ Interactive Spatial Map
- Visual map view centered on Greater London.
- Dynamic color-coded circle markers scaled by borough ranking:
  - 🟢 **Top Match (#1)**: Vibrant Emerald
  - 🔵 **Top Tier (#2–#3)**: Cyan Blue
  - 🟡 **Other Boroughs**: Amber / Slate
- **Interactive Fly-To**: Clicking any borough in the leaderboard smoothly flies the camera to that borough's coordinates and opens a rich detail popup.

---

## 📊 Scoring Methodology & Data Fusion

HappyBorough combines multiple official UK public sector datasets:

1. **ONS Personal Well-being Survey (Office for National Statistics)**: Annual benchmark measuring life satisfaction, worthwhile feelings, and happiness by local authority (scaled 0–10). Curated for a subset of boroughs; the rest use a London-wide average, clearly flagged as `estimated_benchmark` in the API.
2. **UK Police Open Data (live)**: Live `data.police.uk` street-level crime counts, queried per borough and converted into a 0–10 Safety Score, cached for 1 hour. Falls back to a static benchmark (or the IMD Crime domain decile, for boroughs without one) if the live call fails.
3. **Transport for London (TfL) PTAL**: Public Transport Accessibility Level scores measuring access to tube, rail, bus, and tram networks (scaled 0–10).
4. **London Green Spaces & Tree Canopy**: Percentage of municipal area dedicated to public parks, nature reserves, and green infrastructure (scaled 0–10).
5. **Council Planning Portal Dataset (`housing.db`)**: 181,929 historical planning applications (2022–2025) reflecting council development velocity and approval flexibility, for all 33 boroughs.
6. **English Indices of Deprivation 2025 (MHCLG)**: Official small-area (LSOA) deprivation scores across 7 domains — Income, Employment, Education, Health, Crime, **Barriers to Housing and Services**, and Living Environment — aggregated up to all 33 London boroughs by [`build_deprivation_index.py`](build_deprivation_index.py) (population-weighted mean, source rows in [`data/imd2025_london_lsoa.csv`](data/imd2025_london_lsoa.csv), output in [`data/deprivation_borough.json`](data/deprivation_borough.json)). Deciles run 1 (most deprived 10% in England) to 10 (least deprived), matching the app's existing 0–10 scale. This is the source that extends borough coverage from the original 12 curated boroughs to the full 33, and adds the new **Housing & Service Barriers** slider.

### Composite Score Formula
For any set of user weights $(w_{\text{safety}}, w_{\text{green}}, w_{\text{transport}}, w_{\text{happiness}}, w_{\text{barriers}})$ where $\sum w = 1.0$:

$$\text{Score} = (10 \cdot \text{Safety} \cdot w_{\text{safety}}) + (10 \cdot \text{Green} \cdot w_{\text{green}}) + (10 \cdot \text{Transport} \cdot w_{\text{transport}}) + (10 \cdot \text{Happiness} \cdot w_{\text{happiness}}) + (10 \cdot \text{HousingBarriersDecile} \cdot w_{\text{barriers}})$$

---

## 🏗️ Architecture & Technology Stack

| Component | Technology | Description |
|---|---|---|
| **Backend** | Python 3 (`http.server`, `socketserver`) | Lightweight server with zero external framework dependencies |
| **Frontend** | Vanilla JS & HTML5 | Dark mode glassmorphic UI, responsive two-column grid |
| **Mapping** | Leaflet 1.9.4 & OpenStreetMap | Lightweight vector circles, popup cards, and animated fly-to |
| **Typography** | Google Fonts | *Inter* (clean, modern legibility) |
| **Database** | SQLite 3 (`housing.db`) | Cross-references planning volume and approval rate per borough |

---

## 📁 Repository Structure

```
NewSpeak/
├── happiness_server.py             # HappyBorough application server & API (Port 8085)
├── server.py                       # Complementary PlanPulse 3D planning feasibility server (Port 8080)
├── mcp_server.py                   # Model Context Protocol (MCP) server for AI assistants
├── convert_db.py                   # Data ingestion & indexing script (CSV -> SQLite)
├── build_deprivation_index.py      # IMD 2025 LSOA -> borough aggregation script
├── housing.db                      # 118MB indexed SQLite database (181,929 applications)
├── data/
│   ├── imd2025_london_lsoa.csv     # IMD 2025, filtered to London's ~5,000 LSOAs
│   └── deprivation_borough.json    # Aggregated IMD 2025 output, all 33 boroughs
├── .env.example                    # Environment configuration template
├── .gitignore                      # Git ignore rules for bytecode & secrets
└── README.md                       # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.9+** (uses standard library modules only; no pip dependencies required!)

### 2. Launch the HappyBorough Server

```bash
python3 happiness_server.py
```

### 3. Open in Your Browser
Navigate to:
👉 **http://localhost:8085**

Adjust the sliders on the left (Safety, Green Space, Transport, Well-being, Housing & Service Barriers) to explore how the rankings and map update dynamically across all 33 London boroughs!

---

## 📡 REST API Reference

The server exposes a clean JSON endpoint for programmatic integration:

### Get Weighted Borough Rankings

```http
GET /api/rankings?w_safety=0.25&w_green=0.25&w_transport=0.15&w_happiness=0.15&w_barriers=0.20
```

#### Query Parameters:
| Parameter | Type | Default | Description |
|---|---|---|---|
| `w_safety` | `float` | `0.25` | Relative weight for safety & low crime (0.0 – 1.0) |
| `w_green` | `float` | `0.25` | Relative weight for parks & green space (0.0 – 1.0) |
| `w_transport` | `float` | `0.15` | Relative weight for public transport access (0.0 – 1.0) |
| `w_happiness` | `float` | `0.15` | Relative weight for ONS community happiness (0.0 – 1.0) |
| `w_barriers` | `float` | `0.20` | Relative weight for IMD 2025 Housing & Service Barriers decile (0.0 – 1.0) |

#### Sample Response:
```json
[
  {
    "borough": "Richmond upon Thames",
    "overall_score": 88.0,
    "ons_happiness": 7.7,
    "estimated_benchmark": false,
    "safety_score": 9.4,
    "safety_source": "live_api",
    "recent_crimes": 280,
    "green_space": 9.4,
    "transport_score": 6.8,
    "housing_apps": 4866,
    "housing_approval_rate": 76.6,
    "lat": 51.4479,
    "lng": -0.3260,
    "imd": {
      "overall_decile": 8.16,
      "income_decile": 7.72,
      "employment_decile": 8.11,
      "education_decile": 9.25,
      "health_decile": 9.27,
      "crime_decile": 6.92,
      "housing_barriers_decile": 9.6,
      "living_environment_decile": 2.61,
      "population": 195165
    }
  },
  {
    "borough": "Newham",
    "overall_score": 64.9,
    "ons_happiness": 7.05,
    "estimated_benchmark": true,
    "safety_score": 6.1,
    "safety_source": "live_api",
    "green_space": 7.5,
    "transport_score": 7.9,
    "housing_apps": 3380,
    "housing_approval_rate": 88.6,
    "lat": 51.5077,
    "lng": 0.0469,
    "imd": {
      "overall_decile": 2.1,
      "housing_barriers_decile": 5.3,
      "population": 355952
    }
  }
]
```

---

## 💡 Typical Use Cases

- **Homebuyers & Renters**: Discover London neighborhoods that match your lifestyle instead of relying only on property price filters.
- **Relocators**: Moving to London from abroad or other UK cities and trying to understand borough trade-offs (e.g. green space vs. central tube lines).
- **Families**: Prioritize safety ratings and parkland density to shortlist council areas.
- **Urban Planners & Policy Teams**: Assess the relationship between neighborhood well-being, transit accessibility, and housing delivery rates.

---

## 🔗 Related Components in This Repository

- **[server.py](server.py)**: PlanPulse London — a hyper-local planning feasibility and 3D precedent engine powered by Mapbox GL JS v3 and 181k+ council records.
- **[mcp_server.py](mcp_server.py)**: Model Context Protocol (MCP) server enabling AI assistants (Claude, Antigravity, Cursor) to query borough statistics and precedents via natural language.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Public benchmarks are derived from official UK Open Data (ONS, UK Police Open Data, TfL) licensed under the [Open Government Licence (OGL)](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
