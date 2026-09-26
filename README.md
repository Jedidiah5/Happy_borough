# 😊 HappyBorough London — Legal Neighborhood Vibe & Happiness Index

> **Multi-factor open data fusion platform for ranking London's happiest, safest, and most livable boroughs based on your personalized lifestyle priorities.**

![Platform](https://img.shields.io/badge/Platform-Greater%20London-10B981?style=flat-square)
![Data Fusion](https://img.shields.io/badge/Open%20Data-ONS%20%2B%20Police%20%2B%20TfL%20%2B%20GLA%20Rents%20%2B%20Planning-38BDF8?style=flat-square)
![Architecture](https://img.shields.io/badge/Stack-Python%20%2B%20Leaflet%20%2B%20SQLite-0284C7?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-slate?style=flat-square)

---

## 📌 Overview

Choosing where to live or invest in London is often reduced to house prices and rent costs. **HappyBorough London** changes that by fusing official UK open data benchmarks into a personalized, interactive livability and happiness engine.

By combining well-being surveys, crime statistics, public transport accessibility, and urban green canopy density with official council planning metrics, HappyBorough enables citizens, homebuyers, and urban researchers to find the neighborhood that aligns with their personal lifestyle values.

---

## 🌟 Key Features

### 🎛️ Personalized Priority Weighting
- **Real-Time Sliders**: Adjust relative weights across 6 key livability dimensions:
  - 🛡️ **Safety & Low Crime** (live UK Police Open Data)
  - 🌳 **Parks & Green Space** (canopy and open parkland density)
  - 🚆 **Public Transport Accessibility** (TfL PTAL connectivity ratings)
  - 😊 **ONS Life Satisfaction** (Personal Well-being Survey, real per-borough data)
  - 🏘️ **Housing & Service Barriers** (English Indices of Deprivation 2025)
  - 💷 **Affordability** (GLA/ONS private rents, cheaper = higher score)
- **Instant Recalculation**: Live dynamic re-weighting and normalization so sliders always sum to 100%.

### 🏆 Dynamic Borough Leaderboard
- Real-time ranked list of top-matched London boroughs based on your current slider weights.
- Composite **Happiness Score (0–100)** for each borough.
- Detailed metric breakdowns: safety score, green space index, transport connectivity, and ONS life satisfaction.
- Integrated council planning approval rates and application volumes queried live from `housing.db`.

### 🗺️ Interactive Spatial Map
- Visual map view centered on Greater London, with two switchable modes:
  - **🏙️ Boroughs**: dynamic color-coded circle markers scaled by borough ranking (🟢 Top Match #1, 🔵 Top Tier #2–#3, 🟡 everyone else).
  - **🔬 Neighborhoods**: a true small-area choropleth of all 4,994 London LSOAs (~1,500 people each), shaded by any of 8 IMD 2025 domains via a picker (Overall, Income, Employment, Education, Health, Crime, Housing & Service Barriers, Living Environment) — click any polygon for its exact decile.
- **Interactive Fly-To**: Clicking any borough in the leaderboard smoothly flies the camera to that borough's coordinates and opens a rich detail popup.

---

## 📊 Scoring Methodology & Data Fusion

HappyBorough combines multiple official UK public sector datasets:

1. **ONS Personal Well-being Survey (Office for National Statistics)**: Real annual survey data (2011-12 to 2022-23) for Life satisfaction, Happiness, Worthwhile, and Anxiety, scaled 0–10, for 32 of 33 boroughs, aggregated by [`build_wellbeing_index.py`](build_wellbeing_index.py) from [`data/ons_wellbeing_london_boroughs.csv`](data/ons_wellbeing_london_boroughs.csv) into [`data/wellbeing_borough.json`](data/wellbeing_borough.json). The City of London's population (~8,000) is too small for ONS to publish a reliable local estimate for any measure or year, so it falls back to a London-wide average, flagged `estimated` in the API.
2. **UK Police Open Data (live)**: Live `data.police.uk` street-level crime counts, queried per borough and converted into a 0–10 Safety Score, cached for 1 hour. Falls back to a static benchmark (or the IMD Crime domain decile, for boroughs without one) if the live call fails.
3. **Transport for London (TfL) PTAL**: Public Transport Accessibility Level scores measuring access to tube, rail, bus, and tram networks (scaled 0–10).
4. **London Green Spaces & Tree Canopy**: Percentage of municipal area dedicated to public parks, nature reserves, and green infrastructure (scaled 0–10).
5. **Council Planning Portal Dataset (`housing.db`)**: 181,929 historical planning applications (2022–2025) reflecting council development velocity and approval flexibility, for all 33 boroughs.
6. **English Indices of Deprivation 2025 (MHCLG)**: Official small-area (LSOA) deprivation scores across 7 domains — Income, Employment, Education, Health, Crime, **Barriers to Housing and Services**, and Living Environment — aggregated up to all 33 London boroughs by [`build_deprivation_index.py`](build_deprivation_index.py) (population-weighted mean, source rows in [`data/imd2025_london_lsoa.csv`](data/imd2025_london_lsoa.csv), output in [`data/deprivation_borough.json`](data/deprivation_borough.json)). Deciles run 1 (most deprived 10% in England) to 10 (least deprived), matching the app's existing 0–10 scale.
7. **GLA "Housing in London 2025" / ONS Price Index of Private Rents**: Average monthly private rent by bedroom count (Sept 2024–Aug 2025) for 32 of 33 boroughs, aggregated by [`build_rent_index.py`](build_rent_index.py) from [`data/london_borough_rents_2025.csv`](data/london_borough_rents_2025.csv) into [`data/rent_borough.json`](data/rent_borough.json). Converted into a 0–10 **Affordability score** (cheapest borough = 10, priciest = 0). ONS doesn't publish a City of London figure either, so it uses the same flagged London-wide average fallback.
8. **ONS Open Geography Portal — LSOA boundaries & population-weighted centroids**: The same IMD 2025 data above, but rendered at its native small-area resolution instead of aggregated to borough level. [`build_lsoa_choropleth.py`](build_lsoa_choropleth.py) joins [`data/lsoa_boundaries_london.geojson`](data/lsoa_boundaries_london.geojson) (generalised polygon boundaries) and [`data/lsoa_pop_centroids_london.geojson`](data/lsoa_pop_centroids_london.geojson) with the LSOA-level IMD rows into [`data/lsoa_choropleth.json`](data/lsoa_choropleth.json) — all 4,994 London LSOAs, served lazily to the map's **Neighborhoods** view via `/api/lsoa-geo`.

### Composite Score Formula
For any set of user weights $(w_{\text{safety}}, w_{\text{green}}, w_{\text{transport}}, w_{\text{happiness}}, w_{\text{barriers}}, w_{\text{afford}})$ where $\sum w = 1.0$:

$$\text{Score} = (10 \cdot \text{Safety} \cdot w_{\text{safety}}) + (10 \cdot \text{Green} \cdot w_{\text{green}}) + (10 \cdot \text{Transport} \cdot w_{\text{transport}}) + (10 \cdot \text{LifeSatisfaction} \cdot w_{\text{happiness}}) + (10 \cdot \text{HousingBarriersDecile} \cdot w_{\text{barriers}}) + (10 \cdot \text{Affordability} \cdot w_{\text{afford}})$$

---

## 🏗️ Architecture & Technology Stack

| Component | Technology | Description |
|---|---|---|
| **Backend** | Python 3 (`http.server`, `socketserver`) | Lightweight server with zero external framework dependencies |
| **Frontend** | Vanilla JS & HTML5 | Dark mode glassmorphic UI, responsive two-column grid |
| **Mapping** | Leaflet 1.9.4 & OpenStreetMap | Vector circles, a 4,994-polygon GeoJSON choropleth, popup cards, and animated fly-to |
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
├── build_wellbeing_index.py        # ONS well-being time series -> borough aggregation script
├── build_rent_index.py             # GLA/ONS borough rents -> affordability score script
├── build_lsoa_choropleth.py        # LSOA boundaries + centroids + IMD -> neighborhood choropleth script
├── housing.db                      # 118MB indexed SQLite database (181,929 applications)
├── data/
│   ├── imd2025_london_lsoa.csv             # IMD 2025, filtered to London's ~5,000 LSOAs
│   ├── deprivation_borough.json            # Aggregated IMD 2025 output, all 33 boroughs
│   ├── ons_wellbeing_london_boroughs.csv   # ONS well-being survey, filtered to London boroughs
│   ├── wellbeing_borough.json              # Aggregated ONS well-being output, 32 of 33 boroughs
│   ├── london_borough_rents_2025.csv       # GLA "Housing in London 2025" borough rent table
│   ├── rent_borough.json                   # Aggregated rent/affordability output, all 33 boroughs
│   ├── lsoa_boundaries_london.geojson      # LSOA polygon boundaries, filtered to London's 4,994 LSOAs
│   ├── lsoa_pop_centroids_london.geojson   # LSOA population-weighted centroids, same 4,994 LSOAs
│   └── lsoa_choropleth.json                # Boundaries + centroids + IMD joined, served by /api/lsoa-geo
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

Adjust the sliders on the left (Safety, Green Space, Transport, Life Satisfaction, Housing & Service Barriers, Affordability) to explore how the rankings and map update dynamically across all 33 London boroughs!

---

## 📡 REST API Reference

The server exposes a clean JSON endpoint for programmatic integration:

### Get Weighted Borough Rankings

```http
GET /api/rankings?w_safety=0.20&w_green=0.20&w_transport=0.15&w_happiness=0.15&w_barriers=0.15&w_affordability=0.15
```

#### Query Parameters:
| Parameter | Type | Default | Description |
|---|---|---|---|
| `w_safety` | `float` | `0.20` | Relative weight for safety & low crime (0.0 – 1.0) |
| `w_green` | `float` | `0.20` | Relative weight for parks & green space (0.0 – 1.0) |
| `w_transport` | `float` | `0.15` | Relative weight for public transport access (0.0 – 1.0) |
| `w_happiness` | `float` | `0.15` | Relative weight for ONS Life Satisfaction (0.0 – 1.0) |
| `w_barriers` | `float` | `0.15` | Relative weight for IMD 2025 Housing & Service Barriers decile (0.0 – 1.0) |
| `w_affordability` | `float` | `0.15` | Relative weight for private-rent affordability (0.0 – 1.0) |

#### Sample Response:
```json
[
  {
    "borough": "Richmond upon Thames",
    "overall_score": 82.7,
    "ons_happiness": 7.29,
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
    "wellbeing": {
      "latest_year": "2022-23",
      "life_satisfaction": 7.29,
      "happiness": 7.42,
      "worthwhile": 7.66,
      "anxiety": 2.71,
      "life_satisfaction_trend": [["2011-12", 7.61], "...", ["2022-23", 7.29]],
      "estimated": false
    },
    "affordability_score": 6.35,
    "rent": {
      "typical_monthly": 2444.5,
      "rent_1bed": 1593,
      "rent_2bed": 2048,
      "rent_3bed": 2476,
      "rent_4plusbed": 3661,
      "estimated": false
    },
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
    "borough": "City of London",
    "overall_score": 81.7,
    "ons_happiness": 7.36,
    "estimated_benchmark": true,
    "safety_score": 9.5,
    "safety_source": "live_api",
    "green_space": 8.38,
    "transport_score": 8.11,
    "housing_apps": 0,
    "housing_approval_rate": 75.0,
    "lat": 51.5155,
    "lng": -0.0922,
    "wellbeing": {
      "latest_year": null,
      "life_satisfaction": 7.36,
      "happiness": 7.32,
      "worthwhile": 7.61,
      "anxiety": 3.36,
      "life_satisfaction_trend": [],
      "estimated": true
    },
    "affordability_score": 7.24,
    "rent": {
      "typical_monthly": 2249.42,
      "rent_1bed": 1568.25,
      "rent_2bed": 1970.47,
      "rent_3bed": 2304.31,
      "rent_4plusbed": 3154.66,
      "estimated": true
    },
    "imd": {
      "overall_decile": 7.89,
      "housing_barriers_decile": 7.89,
      "population": 8072
    }
  }
]
```

`wellbeing.estimated` and `rent.estimated` are only ever `true` for the City of London: its resident population (~8,000) is too small for ONS to publish either a well-being or a private-rent estimate, so both fall back to a flagged London-wide average.

### Get Neighborhood (LSOA) Choropleth Geometry

```http
GET /api/lsoa-geo
```

Returns a static GeoJSON `FeatureCollection` of all 4,994 London LSOAs (population ~1,500 each), fetched lazily by the map's **🔬 Neighborhoods** view. Each feature's `properties` carries `lsoa_code`, `lsoa_name`, `borough`, a population-weighted `centroid` (`[lng, lat]`), and a `domains` object with `{score, decile}` for `imd`, `income`, `employment`, `education`, `health`, `crime`, `housing_barriers`, and `living_environment` — the same domains as the borough-level `imd` object above, just at native small-area resolution instead of population-weighted up to borough.

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
