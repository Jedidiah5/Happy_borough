let map = L.map('map').setView([51.5074, -0.1278], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map);
let markersGroup = L.layerGroup().addTo(map);
let searchMarker = null;
let currentRankings = [];
let boroughMarkers = {};

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
    currentRankings = data;

    markersGroup.clearLayers();
    boroughMarkers = {};
    const listEl = document.getElementById('rankings-list');
    listEl.innerHTML = '';

    data.forEach((b, idx) => {
        const isLive = b.safety_source === 'live_api';
        const crimeDetail = b.recent_crimes !== null ? `(${b.recent_crimes} crimes reported this month)` : '(Benchmark fallback)';

        const m = L.circleMarker([b.lat, b.lng], {
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

        boroughMarkers[b.borough] = m;

        const item = document.createElement('div');
        item.className = 'borough-item';
        item.dataset.borough = b.borough;
        item.onclick = () => {
            clearHighlight();
            item.classList.add('active-highlight');
            map.flyTo([b.lat, b.lng], 13.5);
            m.openPopup();
        };
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

function clearHighlight() {
    document.querySelectorAll('.borough-item').forEach(el => el.classList.remove('active-highlight'));
}

async function executeSearch(query) {
    if (!query) query = document.getElementById('search-input').value.trim();
    if (!query) {
        resetSearch();
        return;
    }

    const feedbackEl = document.getElementById('search-feedback');
    const clearBtn = document.getElementById('search-clear-btn');
    clearBtn.style.display = 'block';

    feedbackEl.style.display = 'block';
    feedbackEl.className = 'search-feedback searching';
    feedbackEl.innerHTML = `🔍 Searching coordinates for "<b>${escapeHtml(query)}</b>"...`;

    try {
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
        const result = await res.json();

        if (!result.found) {
            feedbackEl.className = 'search-feedback error';
            feedbackEl.innerHTML = `⚠️ ${result.message || 'No matching London borough or UK postcode found.'}`;
            return;
        }

        // Clean up previous search pin if any
        if (searchMarker) {
            map.removeLayer(searchMarker);
            searchMarker = null;
        }

        // Fly map smoothly to location
        map.flyTo([result.lat, result.lng], 13.5);

        // Add custom pulsating search marker
        const pinIcon = L.divIcon({
            className: 'search-pin-wrapper',
            html: `
                <div style="
                    background: #EF4444;
                    color: #FFFFFF;
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 0 14px rgba(239, 68, 68, 0.8), 0 0 0 4px rgba(239, 68, 68, 0.25);
                    font-size: 16px;
                    border: 2px solid #FFFFFF;
                    cursor: pointer;
                ">📍</div>
            `,
            iconSize: [32, 32],
            iconAnchor: [16, 16]
        });

        searchMarker = L.marker([result.lat, result.lng], { icon: pinIcon }).addTo(map);

        const distText = result.distance_km > 0 ? ` (~${result.distance_km}km from ${result.borough})` : '';
        searchMarker.bindPopup(`
            <div style="font-size: 0.95rem; font-weight: 700; color: #38BDF8; margin-bottom: 4px;">📍 ${escapeHtml(result.matched_name)}</div>
            <div style="font-size: 0.82rem; margin-bottom: 6px; color: #E2E8F0;">
                <b>Tracked Borough:</b> ${escapeHtml(result.borough)}${distText}
            </div>
            <div style="font-size: 0.8rem; line-height: 1.5; color: #CBD5E1;">
                🛡️ Safety Score: <b>${result.safety}/10</b><br/>
                🌳 Green Space: <b>${result.green_space}/10</b><br/>
                🚆 Transport Access: <b>${result.transport}/10</b><br/>
                😊 Community Satisfaction: <b>${result.happiness}/10</b>
            </div>
        `).openPopup();

        feedbackEl.className = 'search-feedback success';
        feedbackEl.innerHTML = `✅ Found: <b>${escapeHtml(result.matched_name)}</b><br/><small style="color: #CBD5E1;">Matched to <b>${escapeHtml(result.borough)}</b>${distText}</small>`;

        // Highlight matching borough in the leaderboard and scroll into view
        clearHighlight();
        const matchedItem = document.querySelector(`.borough-item[data-borough="${result.borough}"]`);
        if (matchedItem) {
            matchedItem.classList.add('active-highlight');
            matchedItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

    } catch (err) {
        feedbackEl.className = 'search-feedback error';
        feedbackEl.innerHTML = `⚠️ Search request failed: ${escapeHtml(err.message)}`;
    }
}

function resetSearch() {
    const input = document.getElementById('search-input');
    const feedbackEl = document.getElementById('search-feedback');
    const clearBtn = document.getElementById('search-clear-btn');

    input.value = '';
    clearBtn.style.display = 'none';
    feedbackEl.style.display = 'none';
    feedbackEl.className = 'search-feedback';

    if (searchMarker) {
        map.removeLayer(searchMarker);
        searchMarker = null;
    }
    clearHighlight();

    // Show all items in leaderboard
    document.querySelectorAll('.borough-item').forEach(item => item.style.display = 'flex');

    // Reset map view
    map.flyTo([51.5074, -0.1278], 11);
}

function quickSearch(term) {
    const input = document.getElementById('search-input');
    input.value = term;
    executeSearch(term);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m];
    });
}

// Setup Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const clearBtn = document.getElementById('search-clear-btn');

    if (searchBtn) {
        searchBtn.addEventListener('click', () => executeSearch(searchInput.value));
    }

    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                executeSearch(searchInput.value);
            }
        });

        // Real-time client-side filter of the leaderboard list
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.trim().toLowerCase();
            clearBtn.style.display = query ? 'block' : 'none';

            if (!query) {
                document.querySelectorAll('.borough-item').forEach(item => item.style.display = 'flex');
                return;
            }

            document.querySelectorAll('.borough-item').forEach(item => {
                const bName = (item.dataset.borough || '').toLowerCase();
                if (bName.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', resetSearch);
    }
});

updateRankings();
