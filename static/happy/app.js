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
