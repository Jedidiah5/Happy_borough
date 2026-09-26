# 😊 HappyBorough London — Legal Neighborhood Vibe & Happiness Index

> **Multi-factor open data fusion platform for ranking London's happiest, safest, and most livable boroughs based on your personalized lifestyle priorities.**

![Platform](https://img.shields.io/badge/Platform-Greater%20London-10B981?style=flat-square)
![Data Fusion](https://img.shields.io/badge/Open%20Data-ONS%20%2B%20Police%20%2B%20TfL%20%2B%20GLA%20Rents%20%2B%20Planning-38BDF8?style=flat-square)
![Architecture](https://img.shields.io/badge/Stack-Python%20%2B%20Three.js%20%2B%20SQLite-0284C7?style=flat-square)
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
  - 🌳 **Parks & Green Space** (OS Open Greenspace, real per-borough data for all 33 boroughs)
  - 🚆 **Public Transport Accessibility** (TfL PTAL, population-weighted from ward level to all 33 boroughs)
  - 😊 **ONS Life Satisfaction** (Personal Well-being Survey, real per-borough data)
  - 🏘️ **Housing & Service Barriers** (English Indices of Deprivation 2025)
  - 💷 **Affordability** (GLA/ONS private rents, cheaper = higher score)
- **Instant Recalculation**: Sliders are normalised to sum to 100%. While you drag, the browser re-scores every borough locally with the same formula as the server. When you let go, the page refetches `/api/rankings` to confirm with live data. The panel shows "✓ Confirmed by server", and the console warns if the two scores ever differ by more than 0.1.

### 🏙️ 3D London City View (Three.js)
- Every borough is a glowing tower placed by its real latitude/longitude; **tower height = overall score**.
- Towers rise in a staggered wave on load, and re-grow, re-colour and re-glow live as you move the sliders.
- The top 3 boroughs glow brighter, and a light beam marks **#1**.
- Slow auto-orbit with drag, zoom and pan controls, fog, bloom, and floating borough labels.
- Hover a tower for a tooltip. Click a tower (or a leaderboard row) to fly the camera to it and open the detail card.
- Respects `prefers-reduced-motion`, caps pixel ratio at 2 for performance, and falls back to a list-only layout if WebGL is unavailable.

### 🏆 Dynamic Borough Leaderboard
- Real-time ranked list of all 33 boroughs based on your current slider weights, with smooth reordering animations.
- Composite **Happiness Score (0–100)** for each borough, plus a "Live police" / "Benchmark fallback" tag showing where its safety data came from.

### 🗂️ Borough Detail Card
- Six animated bars, one per factor: safety, green space, transport, wellbeing, housing access and affordability.
- Typical monthly rent (with 1-bed and 2-bed figures), green space % of land with mapped site count, ONS life satisfaction with its trend, anxiety and "worthwhile" scores, and IMD 2025 deprivation deciles. Values that are estimated are tagged "est.".

### 🔬 Neighborhood-Level Data (API-ready)
- Underneath the borough view, the IMD 2025 domains above are also available at their native small-area resolution: all 4,994 London LSOAs (~1,500 people each), across all 8 domains (Overall, Income, Employment, Education, Health, Crime, Housing & Service Barriers, Living Environment).
- Served via [`/api/lsoa-geo`](#get-neighborhood-lsoa-choropleth-geometry) as a single GeoJSON payload (polygon boundaries + population-weighted centroids + deciles per LSOA) — currently a data/API capability without a 3D-scene visualization yet; a previous Leaflet-based 2D "Neighborhoods" map view consumed this same endpoint and is a natural reference for a future 3D-native version.

---

## 📊 Scoring Methodology & Data Fusion

HappyBorough combines multiple official UK public sector datasets:

1. **ONS Personal Well-being Survey (Office for National Statistics)**: Real annual survey data (2011-12 to 2022-23) for Life satisfaction, Happiness, Worthwhile, and Anxiety, scaled 0–10, for 32 of 33 boroughs, aggregated by [`build_wellbeing_index.py`](build_wellbeing_index.py) from [`data/ons_wellbeing_london_boroughs.csv`](data/ons_wellbeing_london_boroughs.csv) into [`data/wellbeing_borough.json`](data/wellbeing_borough.json). The City of London's population (~8,000) is too small for ONS to publish a reliable local estimate for any measure or year, so it falls back to a London-wide average, flagged `estimated` in the API.
2. **UK Police Open Data (live)**: Live `data.police.uk` street-level crime counts, queried per borough and converted into a 0–10 Safety Score, cached for 1 hour. Falls back to a static benchmark (or the IMD Crime domain decile, for boroughs without one) if the live call fails.
3. **Transport for London (TfL) Public Transport Accessibility Levels (PTAL)**: TfL's official 0/1a/1b/2/3/4/5/6a/6b accessibility bands and underlying continuous Accessibility Index, aggregated by [`build_transport_index.py`](build_transport_index.py) from [`data/tfl_ward_ptal_2023.geojson`](data/tfl_ward_ptal_2023.geojson) (704 wards, December 2024 boundaries). Wards carry no borough field, so each of London's 4,994 LSOA population-weighted centroids ([`data/lsoa_pop_centroids_london.geojson`](data/lsoa_pop_centroids_london.geojson)) is spatially joined to the ward polygon it falls inside, then rolled up to its borough with the same population-weighted mean [`build_deprivation_index.py`](build_deprivation_index.py) uses for IMD, into [`data/transport_borough.json`](data/transport_borough.json). Real data for all 33 boroughs — this replaces the previous approach of hand-typing a 0–10 guess for 12 boroughs and averaging those 12 for the rest, which the README had (inaccurately) also labelled "TfL PTAL" despite no link to any TfL dataset. The Accessibility Index is rescaled 0–10 by min-max **excluding City of London**, whose Square Mile is such an extreme outlier (~2.5× the next borough) that including it would compress the other 32 boroughs' real spread into a sliver of the scale; City of London itself is clamped to 10. Requires `geopandas` + `shapely` to regenerate (`pip install geopandas shapely`) — the only build script in this repo with a non-stdlib dependency; not needed to just run the server, since it reads the pre-built JSON.
4. **OS Open Greenspace (Ordnance Survey)**: Real per-site park/open-space polygons for all of Great Britain, reduced to the 11,152 sites falling inside a London borough and summed into a green space area, for all 33 boroughs, aggregated by [`build_greenspace_index.py`](build_greenspace_index.py) from [`data/os_greenspace_borough_raw.csv`](data/os_greenspace_borough_raw.csv) into [`data/greenspace_borough.json`](data/greenspace_borough.json). Converted into a 0–10 **Green space score** (green space area as a % of borough land area, min-max normalized: greenest borough = 10, least green = 0). This replaces the old 12-borough hand-typed guess and 21-borough average — green space is now sourced exactly like every other metric in this app.
5. **Council Planning Portal Dataset (`housing.db`)**: 181,929 historical planning applications (2022–2025) reflecting council development velocity and approval flexibility, for all 33 boroughs.
6. **English Indices of Deprivation 2025 (MHCLG)**: Official small-area (LSOA) deprivation scores across 7 domains — Income, Employment, Education, Health, Crime, **Barriers to Housing and Services**, and Living Environment — aggregated up to all 33 London boroughs by [`build_deprivation_index.py`](build_deprivation_index.py) (population-weighted mean, source rows in [`data/imd2025_london_lsoa.csv`](data/imd2025_london_lsoa.csv), output in [`data/deprivation_borough.json`](data/deprivation_borough.json)). Deciles run 1 (most deprived 10% in England) to 10 (least deprived), matching the app's existing 0–10 scale.
7. **GLA "Housing in London 2025" / ONS Price Index of Private Rents**: Average monthly private rent by bedroom count (Sept 2024–Aug 2025) for 32 of 33 boroughs, aggregated by [`build_rent_index.py`](build_rent_index.py) from [`data/london_borough_rents_2025.csv`](data/london_borough_rents_2025.csv) into [`data/rent_borough.json`](data/rent_borough.json). Converted into a 0–10 **Affordability score** (cheapest borough = 10, priciest = 0). ONS doesn't publish a City of London figure either, so it uses the same flagged London-wide average fallback.
8. **ONS Open Geography Portal — LSOA boundaries & population-weighted centroids**: The same IMD 2025 data above, but at its native small-area resolution instead of aggregated to borough level. [`build_lsoa_choropleth.py`](build_lsoa_choropleth.py) joins [`data/lsoa_boundaries_london.geojson`](data/lsoa_boundaries_london.geojson) (generalised polygon boundaries) and [`data/lsoa_pop_centroids_london.geojson`](data/lsoa_pop_centroids_london.geojson) with the LSOA-level IMD rows into [`data/lsoa_choropleth.json`](data/lsoa_choropleth.json) — all 4,994 London LSOAs, served via `/api/lsoa-geo`. Not yet consumed by the 3D frontend (see below).

### Composite Score Formula
For any set of user weights $(w_{\text{safety}}, w_{\text{green}}, w_{\text{transport}}, w_{\text{happiness}}, w_{\text{barriers}}, w_{\text{afford}})$ where $\sum w = 1.0$:

$$\text{Score} = (10 \cdot \text{Safety} \cdot w_{\text{safety}}) + (10 \cdot \text{Green} \cdot w_{\text{green}}) + (10 \cdot \text{Transport} \cdot w_{\text{transport}}) + (10 \cdot \text{LifeSatisfaction} \cdot w_{\text{happiness}}) + (10 \cdot \text{HousingBarriersDecile} \cdot w_{\text{barriers}}) + (10 \cdot \text{Affordability} \cdot w_{\text{afford}})$$

---

## 🏗️ Architecture & Technology Stack

| Component | Technology | Description |
|---|---|---|
| **Backend** | Python 3 (`http.server`, `socketserver`) | Threaded server with zero external framework dependencies; serves the API and the static frontend |
| **Frontend** | Vanilla JS (ES modules) & HTML5 | Dark glassmorphic UI in `static/happy/`, no build step |
| **3D Scene** | Three.js r169 (via jsDelivr importmap) | Borough towers, OrbitControls, CSS2D labels, bloom post-processing |
| **Neighborhood Geometry** | GeoJSON (served, not yet visualized) | 4,994-polygon LSOA choropleth data via `/api/lsoa-geo`, ready for a future 3D or map layer |
| **Deployment** | Vercel Python function / Docker | `api/index.py` + `vercel.json`, or the `Dockerfile` |
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
├── build_greenspace_index.py       # OS Open Greenspace sites -> green space % + score script
├── build_transport_index.py        # TfL PTAL ward data -> borough transport score script (needs geopandas/shapely)
├── build_lsoa_choropleth.py        # LSOA boundaries + centroids + IMD -> neighborhood choropleth script
├── housing.db                      # 118MB indexed SQLite database (181,929 applications, Git LFS)
├── static/happy/                   # HappyBorough frontend (served at / by happiness_server.py)
│   ├── index.html                  # Page shell + Three.js importmap
│   ├── styles.css                  # Glassmorphic UI, detail card, responsive layout
│   └── js/
│       ├── main.js                 # App state, API fetch, server cross-check
│       ├── scoring.js              # FACTORS list + client copy of the scoring formula
│       ├── scene.js                # Three.js 3D city (towers, beam, camera fly-to)
│       ├── londonMap.js            # 3D flat London map board (borough outlines, search fly-to)
│       ├── flatMap.js              # 2D map view helpers
│       ├── ui.js                   # Sliders, leaderboard, detail card
│       └── tween.js                # Tiny animation engine + reduced-motion check
├── api/index.py                    # Vercel serverless entry point (APP_CHOICE selects the app)
├── vercel.json                     # Vercel routing + bundles static/ with the function
├── Dockerfile                      # Container image (APP_FILE selects the app)
├── data/
│   ├── imd2025_london_lsoa.csv             # IMD 2025, filtered to London's ~5,000 LSOAs
│   ├── deprivation_borough.json            # Aggregated IMD 2025 output, all 33 boroughs
│   ├── ons_wellbeing_london_boroughs.csv   # ONS well-being survey, filtered to London boroughs
│   ├── wellbeing_borough.json              # Aggregated ONS well-being output, 32 of 33 boroughs
│   ├── london_borough_rents_2025.csv       # GLA "Housing in London 2025" borough rent table
│   ├── rent_borough.json                   # Aggregated rent/affordability output, all 33 boroughs
│   ├── os_greenspace_borough_raw.csv       # OS Open Greenspace, aggregated to London borough area/site counts
│   ├── greenspace_borough.json             # Green space % + 0-10 score output, all 33 boroughs
│   ├── tfl_ward_ptal_2023.geojson          # TfL PTAL, ward-aggregated (704 wards, Dec 2024 boundaries)
│   ├── transport_borough.json              # Aggregated transport accessibility output, all 33 boroughs
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
- **Python 3.9+** (the server itself uses standard library modules only; no pip dependencies required to run it!)
- Regenerating `data/transport_borough.json` from source (`python build_transport_index.py`) additionally needs `pip install geopandas shapely` — the one build script in this repo that isn't pure stdlib. Not needed unless you're rebuilding the transport data itself.

### 2. Launch the HappyBorough Server

```bash
python3 happiness_server.py
```

On Windows (PowerShell):

```powershell
python happiness_server.py
```

Set the `PORT` environment variable to use a port other than 8085.

### 3. Open in Your Browser
Navigate to:
👉 **http://localhost:8085**

The first load takes a few seconds while live police data is fetched concurrently for all 33 boroughs (then cached for an hour). Adjust the sliders on the left (Safety, Green Space, Transport, Wellbeing, Housing Access, Affordable Rent) to watch the 3D city and leaderboard re-rank instantly, then click any tower or row for the full borough breakdown.

An internet connection is needed for the Three.js and Google Fonts CDNs.

### 4. Deploy (optional)
- **Vercel**: import the repo (framework preset **Other**, no build command) or run `vercel --prod`. `vercel.json` routes every request to `api/index.py` (London region `lhr1`, 30 s max duration) and bundles `static/`, `data/*.json` and `housing.db`; `.vercelignore` keeps the raw CSV/GeoJSON sources and build scripts out of the bundle so it stays under the 250 MB function limit.
  - **Enable Git LFS** (Project → Settings → Git → Git LFS) before deploying from Git — otherwise `housing.db` is checked out as an LFS pointer, and planning stats and ward search fall back to placeholders (a warning is logged). CLI deploys upload your local copy, so run `git lfs pull` first.
  - Serves HappyBorough by default. Set `APP_CHOICE=server` to serve PlanPulse instead (which also needs `MAPBOX_ACCESS_TOKEN`).
- **Docker**: `docker build -t happyborough . && docker run -p 8080:8080 -e APP_FILE=happiness_server.py happyborough`

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
    "overall_score": 74.5,
    "ons_happiness": 7.29,
    "safety_score": 9.4,
    "safety_source": "live_api",
    "recent_crimes": 280,
    "green_space": 10.0,
    "green_space_pct": 48.6,
    "green_space_sites": 378,
    "transport_score": 0.57,
    "housing_apps": 4866,
    "housing_approval_rate": 76.6,
    "lat": 51.4479,
    "lng": -0.3260,
    "transport": {
      "mean_accessibility_index": 6.33,
      "ptal_band": "2"
    },
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
    "overall_score": 60.1,
    "ons_happiness": 7.36,
    "safety_score": 5.7,
    "safety_source": "live_api",
    "recent_crimes": 2691,
    "green_space": 0.0,
    "green_space_pct": 2.66,
    "green_space_sites": 30,
    "transport_score": 10.0,
    "housing_apps": 0,
    "housing_approval_rate": 75.0,
    "lat": 51.5155,
    "lng": -0.0922,
    "transport": {
      "mean_accessibility_index": 80.59,
      "ptal_band": "6b"
    },
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

`wellbeing.estimated` and `rent.estimated` are only ever `true` for the City of London: its resident population (~8,000) is too small for ONS to publish either a well-being or a private-rent estimate, so both fall back to a flagged London-wide average. Green space (`green_space`/`green_space_pct`/`green_space_sites`, OS Open Greenspace) and transport (`transport_score`/`transport`, TfL PTAL) are both real, sourced data for all 33 boroughs, so neither has an "estimated" flag any more.

### Get Neighborhood (LSOA) Choropleth Geometry

```http
GET /api/lsoa-geo
```

Returns a static GeoJSON `FeatureCollection` of all 4,994 London LSOAs (population ~1,500 each). Each feature's `properties` carries `lsoa_code`, `lsoa_name`, `borough`, a population-weighted `centroid` (`[lng, lat]`), and a `domains` object with `{score, decile}` for `imd`, `income`, `employment`, `education`, `health`, `crime`, `housing_barriers`, and `living_environment` — the same domains as the borough-level `imd` object above, just at native small-area resolution instead of population-weighted up to borough. Not yet wired into the 3D frontend — it's available for a future neighborhood-level view.

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
