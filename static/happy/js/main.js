import { createCityScene } from './scene.js';
import { createFlatMap, LSOA_DOMAINS } from './flatMap.js';
import { initSearch } from './search.js';
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
    view: { mode: 'city', filter: 'all', liveOnly: false },
};

let city = null;
let flatMap = null;

const FILTERS = {
    all: (ranked) => ranked,
    top5: (ranked) => ranked.slice(0, 5),
    top10: (ranked) => ranked.slice(0, 10),
    bottom5: (ranked) => ranked.slice(-5),
};

function visibleSet() {
    const { filter, liveOnly } = state.view;
    if (filter === 'all' && !liveOnly) return null;
    const pool = liveOnly ? state.ranked.filter((b) => b.safety_source === 'live_api') : state.ranked;
    return new Set(FILTERS[filter](pool).map((b) => b.borough));
}

function applyView() {
    const visible = visibleSet();
    city.setVisible(visible);
    flatMap.update(state.ranked, visible);
    for (const row of document.querySelectorAll('.lb-row')) {
        row.classList.toggle('is-filtered', !!visible && !visible.has(row.dataset.borough));
    }
}

function setPressed(button, on) {
    button.classList.toggle('is-on', on);
    button.setAttribute('aria-pressed', String(on));
}

function initDomainPicker() {
    const select = document.getElementById('lsoa-domain');
    select.innerHTML = LSOA_DOMAINS.map((d) => `<option value="${d.value}">${d.label}</option>`).join('');
    select.addEventListener('change', () => {
        if (state.view.mode === 'neighborhoods') flatMap.showNeighborhoods(select.value);
    });
}

function initToolbar() {
    const toolbar = document.querySelector('.toolbar');
    const scoreFilters = document.getElementById('score-filters');
    const liveToggle = document.getElementById('toggle-live');
    const domainPicker = document.getElementById('lsoa-domain');
    for (const btn of toolbar.querySelectorAll('[data-mode]')) {
        btn.addEventListener('click', () => {
            state.view.mode = btn.dataset.mode;
            toolbar.querySelectorAll('[data-mode]').forEach((b) => b.classList.toggle('is-on', b === btn));
            const isFlat = state.view.mode !== 'city';
            const isNeighborhoods = state.view.mode === 'neighborhoods';
            document.body.classList.toggle('mode-map', isFlat);
            document.getElementById('flatmap').hidden = !isFlat;
            scoreFilters.hidden = isNeighborhoods;
            liveToggle.hidden = isNeighborhoods;
            domainPicker.hidden = !isNeighborhoods;
            if (isNeighborhoods) {
                flatMap.show();
                flatMap.showNeighborhoods(domainPicker.value);
            } else if (isFlat) {
                flatMap.show();
                flatMap.showBoroughs();
            }
        });
    }
    for (const btn of toolbar.querySelectorAll('[data-filter]')) {
        btn.addEventListener('click', () => {
            state.view.filter = btn.dataset.filter;
            toolbar.querySelectorAll('[data-filter]').forEach((b) => b.classList.toggle('is-on', b === btn));
            applyView();
        });
    }
    const live = document.getElementById('toggle-live');
    live.addEventListener('click', () => {
        state.view.liveOnly = !state.view.liveOnly;
        setPressed(live, state.view.liveOnly);
        applyView();
    });
    const labels = document.getElementById('toggle-labels');
    labels.addEventListener('click', () => {
        const on = !labels.classList.contains('is-on');
        setPressed(labels, on);
        city.setLabelsVisible(on);
    });
    const board = document.getElementById('toggle-leaderboard');
    board.addEventListener('click', () => {
        const on = !board.classList.contains('is-on');
        setPressed(board, on);
        document.body.classList.toggle('leaderboard-hidden', !on);
    });
}

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
    applyView();
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
    flatMap.focusOn(name);
    markSelectedRow(name);
    showDetail(state.ranked[rank], rank, { opening: true });
}

function clearSelection() {
    state.selected = null;
    markSelectedRow(null);
    hideDetail();
    city.resetView();
    flatMap.resetView();
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
        city = { update() {}, focusOn() {}, resetView() {}, setVisible() {}, setLabelsVisible() {} };
    }
    flatMap = createFlatMap(document.getElementById('flatmap'), { onSelect: selectBorough });
    initDomainPicker();
    initToolbar();
    initDetailCard({ onClose: clearSelection });
    initSearch({
        isReady: () => state.ranked.length > 0,
        onResolved: (result) => {
            if (state.ranked.some((b) => b.borough === result.borough)) selectBorough(result.borough);
        },
        onClear: clearSelection,
    });
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