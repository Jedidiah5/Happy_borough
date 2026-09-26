import { createCityScene } from './scene.js';
import { FACTORS, computeScore, rankBoroughs } from './scoring.js';
import {
    hideDetail,
    initDetailCard,
    initSliders,
    markSelectedRow,
    renderLeaderboard,
    setSyncStatus,
    showDetail,
} from './ui.js';

const SCORE_TOLERANCE = 0.1;

const state = {
    boroughs: [],
    weights: null,
    ranked: [],
    selected: null,
    requestId: 0,
};

let city = null;

async function fetchRankings(weights) {
    const query = new URLSearchParams(FACTORS.map((f) => [f.param, weights[f.key]]));
    const res = await fetch(`/api/rankings?${query}`);
    if (!res.ok) throw new Error(`/api/rankings returned ${res.status}`);
    return res.json();
}

function render(options) {
    state.ranked = rankBoroughs(state.boroughs, state.weights);
    city.update(state.ranked, options);
    renderLeaderboard(state.ranked, { onSelect: selectBorough });
    markSelectedRow(state.selected);
    if (state.selected) {
        const rank = state.ranked.findIndex((b) => b.borough === state.selected);
        if (rank >= 0) showDetail(state.ranked[rank], rank);
    }
}

function selectBorough(name) {
    const rank = state.ranked.findIndex((b) => b.borough === name);
    if (rank < 0) return;
    state.selected = name;
    city.focusOn(name);
    markSelectedRow(name);
    showDetail(state.ranked[rank], rank, { opening: true });
}

function clearSelection() {
    state.selected = null;
    markSelectedRow(null);
    hideDetail();
    city.resetView();
}

function checkAgainstServer(serverRanked, weights) {
    for (const b of serverRanked) {
        const clientScore = computeScore(b, weights);
        if (Math.abs(clientScore - b.overall_score) > SCORE_TOLERANCE) {
            console.warn(
                `[HappyBorough] computeScore disagrees with /api/rankings for ${b.borough}: ` +
                    `client ${clientScore} vs server ${b.overall_score}. Has the server formula changed?`
            );
            return false;
        }
    }
    return true;
}

async function refreshFromServer(weights) {
    const requestId = ++state.requestId;
    setSyncStatus('pending', 'Confirming with live data…');
    try {
        const serverRanked = await fetchRankings(weights);
        if (requestId !== state.requestId) return;
        const agrees = checkAgainstServer(serverRanked, weights);
        state.boroughs = serverRanked;
        render({ animated: true });
        setSyncStatus(agrees ? 'ok' : 'warn', agrees ? '✓ Confirmed by server' : '⚠ Server scores differ (see console)');
    } catch (err) {
        if (requestId !== state.requestId) return;
        console.error(err);
        setSyncStatus('warn', '⚠ Server unreachable, showing last data');
    }
}

async function boot() {
    try {
        city = createCityScene(document.getElementById('scene'), { onSelect: selectBorough });
    } catch (err) {
        console.warn('[HappyBorough] 3D scene unavailable, using list-only layout:', err);
        document.body.classList.add('no-webgl');
        city = { update() {}, focusOn() {}, resetView() {} };
    }
    initDetailCard({ onClose: clearSelection });
    state.weights = initSliders({
        onInput: (weights) => {
            state.weights = weights;
            if (state.boroughs.length) render({ animated: true });
        },
        onCommit: (weights) => {
            state.weights = weights;
            if (state.boroughs.length) refreshFromServer(weights);
        },
    });

    setSyncStatus('pending', 'Loading live data…');
    state.boroughs = await fetchRankings(state.weights);
    render({ animated: true, duration: 900, stagger: 700 });
    setSyncStatus('ok', '✓ Live data loaded');
    document.getElementById('loading').classList.add('is-hidden');
    document.body.classList.add('is-ready');
}

boot().catch((err) => {
    console.error(err);
    document.getElementById('loading').textContent = 'Could not load rankings. Is the server running?';
});
