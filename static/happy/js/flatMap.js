const LONDON = [51.5074, -0.1278];
const HOME_ZOOM = 10;
const LOW = [91, 200, 240];
const HIGH = [140, 198, 63];
const INK = '#3b2a20';

function scoreColor(t) {
    const c = LOW.map((low, i) => Math.round(low + (HIGH[i] - low) * t));
    return `rgb(${c.join(',')})`;
}

// Plain 2D map of London (Leaflet, loaded as a global from the CDN) with one
// dot per borough in the app palette. Created lazily the first time it is shown.
export function createFlatMap(container, { onSelect } = {}) {
    let map = null;
    const markers = new Map();
    let lastRanked = [];
    let lastVisible = null;
    let selected = null;

    function ensureMap() {
        if (map || !window.L) return map;
        map = L.map(container, { zoomControl: false }).setView(LONDON, HOME_ZOOM);
        L.control.zoom({ position: 'bottomleft' }).addTo(map);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19,
        }).addTo(map);
        if (lastRanked.length) update(lastRanked, lastVisible);
        return map;
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
                marker = L.circleMarker([b.lat, b.lng]).addTo(map);
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
            if (shown && !map.hasLayer(marker)) marker.addTo(map);
            if (!shown && map.hasLayer(marker)) marker.remove();
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

    return { update, show, focusOn, resetView };
}
