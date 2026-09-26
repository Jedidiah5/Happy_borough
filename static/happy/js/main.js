import { createCityScene } from './scene.js';
import { computeScore, rankBoroughs } from './scoring.js';
import { initSliders, renderLeaderboard, setSyncStatus } from './ui.js';

const SCORE_TOLERANCE = 0.1;

const state = {
    boroughs: [],
    weights: null,
    ranked: [],
    requestId: 0,
};

let city = null;

async function fetchRankings(weights) {
    const query = new URLSearchParams({
        w_safety: weights.safety,
        w_green: weights.green,
        w_transport: weights.transport,
        w_happiness: weights.happiness,
    });
    const res = await fetch(`/api/rankings?${query}`);
    if (!res.ok) throw new Error(`/api/rankings returned ${res.status}`);
    return res.json();
}

function render(options) {
    state.ranked = rankBoroughs(state.boroughs, state.weights);
    city.update(state.ranked, options);
    renderLeaderboard(state.ranked, { onSelect: selectBorough });
}

function selectBorough(name) {
    console.info('[HappyBorough] selected', name);
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
    city = createCityScene(document.getElementById('scene'));
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
