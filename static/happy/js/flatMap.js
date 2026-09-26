const LONDON = [51.5074, -0.1278];
const HOME_ZOOM = 10;
const LOW = [91, 200, 240];
const HIGH = [140, 198, 63];
const INK = '#3b2a20';

function scoreColor(t) {
    const c = LOW.map((low, i) => Math.round(low + (HIGH[i] - low) * t));
    return `rgb(${c.join(',')})`;
}

// Decile 1 (most deprived) -> 10 (least deprived), red to green -- the
// standard convention for IMD choropleths, independent of the app's own
// cream/blue/green brand palette.
const DECILE_COLORS = ['#a3231b', '#c13d24', '#d9642c', '#e88b3a', '#f0b04a', '#dfc95f', '#b6cf5a', '#8cc63f', '#5c9a2a', '#3f7a1c'];
function colorForDecile(decile) {
    if (decile === null || decile === undefined) return '#c9bfae';
    const idx = Math.min(9, Math.max(0, Math.round(decile) - 1));
    return DECILE_COLORS[idx];
}

export const LSOA_DOMAINS = [
    { value: 'imd', label: 'Overall deprivation' },
    { value: 'income', label: 'Income' },
    { value: 'employment', label: 'Employment' },
    { value: 'education', label: 'Education, skills & training' },
    { value: 'health', label: 'Health & disability' },
    { value: 'crime', label: 'Crime' },
    { value: 'housing_barriers', label: 'Housing & service barriers' },
    { value: 'living_environment', label: 'Living environment' },
];

// Plain 2D map of London (Leaflet, loaded as a global from the CDN) with one
// dot per borough in the app palette, plus an optional LSOA-level (~1,500
// people) IMD 2025 choropleth layer. Created lazily the first time it is shown.
export function createFlatMap(container, { onSelect } = {}) {
    let map = null;
    let markersGroup = null;
    const markers = new Map();
    let lastRanked = [];
    let lastVisible = null;
    let selected = null;

    let lsoaLayer = null;
    let lsoaGeojson = null;
    let lsoaLoadPromise = null;
    let lsoaDomain = 'imd';

    function ensureMap() {
        if (map || !window.L) return map;
        map = L.map(container, { zoomControl: false }).setView(LONDON, HOME_ZOOM);
        L.control.zoom({ position: 'bottomleft' }).addTo(map);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19,
        }).addTo(map);
        markersGroup = L.layerGroup().addTo(map);
        if (lastRanked.length) update(lastRanked, lastVisible);
        return map;
    }

    async function loadLsoaGeojson() {
        if (lsoaGeojson) return lsoaGeojson;
        if (!lsoaLoadPromise) {
            lsoaLoadPromise = fetch('/api/lsoa-geo')
                .then((res) => res.json())
                .then((data) => { lsoaGeojson = data; return data; });
        }
        return lsoaLoadPromise;
    }

    function styleForLsoaFeature(feature) {
        const decile = feature.properties.domains?.[lsoaDomain]?.decile;
        return { fillColor: colorForDecile(decile), fillOpacity: 0.72, color: INK, weight: 0.5 };
    }

    async function showNeighborhoods(domain) {
        lsoaDomain = domain || lsoaDomain;
        ensureMap();
        if (!map) return;
        if (markersGroup && map.hasLayer(markersGroup)) markersGroup.remove();
        const data = await loadLsoaGeojson();
        if (lsoaLayer) {
            lsoaLayer.setStyle(styleForLsoaFeature);
        } else {
            lsoaLayer = L.geoJSON(data, {
                style: styleForLsoaFeature,
                onEachFeature: (feature, layer) => {
                    layer.on('mouseover', () => layer.setStyle({ weight: 2.5, color: '#fff' }));
                    layer.on('mouseout', () => layer.setStyle(styleForLsoaFeature(feature)));
                    const p = feature.properties;
                    layer.bindTooltip(() => {
                        const d = p.domains?.[lsoaDomain];
                        const label = LSOA_DOMAINS.find((x) => x.value === lsoaDomain)?.label || lsoaDomain;
                        return `<strong>${p.lsoa_name}</strong> · ${p.borough}<br>${label}: <strong>${d ? d.decile.toFixed(1) : 'n/a'}/10</strong> <small>(1 = most deprived)</small>`;
                    }, { direction: 'top', className: 'map-tooltip', sticky: true });
                },
            }).addTo(map);
        }
        if (!map.hasLayer(lsoaLayer)) lsoaLayer.addTo(map);
    }

    function showBoroughs() {
        if (lsoaLayer && map && map.hasLayer(lsoaLayer)) lsoaLayer.remove();
        if (markersGroup && map && !map.hasLayer(markersGroup)) markersGroup.addTo(map);
    }

    function markerStyle(rank, t, isSelected) {
        return {
            radius: isSelected ? 15 : rank < 3 ? 12 : 9,
            color: INK,
            weight: rank < 3 || isSelected ? 3 : 1.5,
            fillColor: scoreColor(t),
            fillOpacity: 0.92,
        };
    }

    function update(ranked, visible) {
        lastRanked = ranked;
        lastVisible = visible;
        if (!map) return;
        const scores = ranked.map((b) => b.overall_score);
        const min = Math.min(...scores);
        const range = Math.max(...scores) - min || 1;
        const names = new Set(ranked.map((b) => b.borough));
        for (const [name, marker] of markers) {
            if (!names.has(name)) {
                marker.remove();
                markers.delete(name);
            }
        }
        ranked.forEach((b, rank) => {
            let marker = markers.get(b.borough);
            if (!marker) {
                marker = L.circleMarker([b.lat, b.lng]).addTo(markersGroup);
                marker.on('click', () => onSelect && onSelect(b.borough));
                markers.set(b.borough, marker);
            }
            marker.setStyle(markerStyle(rank, (b.overall_score - min) / range, b.borough === selected));
            marker.setRadius(markerStyle(rank, 0, b.borough === selected).radius);
            marker.bindTooltip(`<strong>#${rank + 1} ${b.borough}</strong><br>${b.overall_score.toFixed(1)} / 100`, {
                direction: 'top',
                offset: [0, -8],
                className: 'map-tooltip',
            });
            const shown = !visible || visible.has(b.borough);
            if (shown && !markersGroup.hasLayer(marker)) marker.addTo(markersGroup);
            if (!shown && markersGroup.hasLayer(marker)) marker.remove();
            if (rank < 3) marker.bringToFront();
        });
    }

    function show() {
        ensureMap();
        if (map) setTimeout(() => map.invalidateSize(), 0);
    }

    function focusOn(name) {
        selected = name;
        const b = lastRanked.find((x) => x.borough === name);
        update(lastRanked, lastVisible);
        if (map && b) map.flyTo([b.lat, b.lng], 12, { duration: 0.9 });
    }

    function resetView() {
        selected = null;
        update(lastRanked, lastVisible);
        if (map) map.flyTo(LONDON, HOME_ZOOM, { duration: 0.9 });
    }

    return { update, show, focusOn, resetView, showNeighborhoods, showBoroughs };
}