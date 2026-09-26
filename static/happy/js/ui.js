import { WEIGHT_KEYS, normaliseWeights } from './scoring.js';
import { prefersReducedMotion } from './tween.js';

export function sourceTagHtml(b) {
    return b.safety_source === 'live_api'
        ? `<span class="source-tag source-live">● Live police · ${b.recent_crimes} crimes</span>`
        : '<span class="source-tag source-fallback">○ Benchmark fallback</span>';
}

const leaderboardRows = new Map();

// Keyed rows + FLIP: measure old positions, reorder, then animate from the old offset.
export function renderLeaderboard(ranked, { onSelect } = {}) {
    const list = document.getElementById('leaderboard');
    const firstTops = new Map();
    for (const [name, row] of leaderboardRows) firstTops.set(name, row.getBoundingClientRect().top);

    const names = new Set(ranked.map((b) => b.borough));
    for (const [name, row] of leaderboardRows) {
        if (!names.has(name)) {
            row.remove();
            leaderboardRows.delete(name);
        }
    }

    ranked.forEach((b, rank) => {
        let row = leaderboardRows.get(b.borough);
        if (!row) {
            row = document.createElement('li');
            row.className = 'lb-row';
            row.dataset.borough = b.borough;
            row.tabIndex = 0;
            row.innerHTML = `
                <span class="lb-rank"></span>
                <div class="lb-main"><div class="lb-name"></div><div class="lb-source"></div></div>
                <span class="lb-score"></span>`;
            row.querySelector('.lb-name').textContent = b.borough;
            row.addEventListener('click', () => onSelect && onSelect(row.dataset.borough));
            row.addEventListener('keydown', (e) => {
                if ((e.key === 'Enter' || e.key === ' ') && onSelect) {
                    e.preventDefault();
                    onSelect(row.dataset.borough);
                }
            });
            leaderboardRows.set(b.borough, row);
        }
        row.querySelector('.lb-rank').textContent = rank + 1;
        row.querySelector('.lb-score').textContent = b.overall_score.toFixed(1);
        row.querySelector('.lb-source').innerHTML = sourceTagHtml(b);
        row.classList.toggle('is-top', rank < 3);
        row.classList.toggle('is-first', rank === 0);
        list.appendChild(row);
    });

    document.getElementById('leaderboard-sub').textContent =
        `${ranked.length} boroughs ranked by your priorities`;

    if (prefersReducedMotion() || firstTops.size === 0) return;
    const moved = [];
    for (const [name, row] of leaderboardRows) {
        if (!firstTops.has(name)) continue;
        const dy = firstTops.get(name) - row.getBoundingClientRect().top;
        if (Math.abs(dy) < 1) continue;
        row.style.transition = 'none';
        row.style.transform = `translateY(${dy}px)`;
        moved.push(row);
    }
    if (!moved.length) return;
    list.getBoundingClientRect();
    requestAnimationFrame(() => {
        for (const row of moved) {
            row.style.transition = '';
            row.style.transform = '';
        }
    });
}

export function initSliders({ onInput, onCommit }) {
    const inputs = WEIGHT_KEYS.map((key) => document.getElementById(`w-${key}`));

    function readWeights() {
        const raw = Object.fromEntries(inputs.map((el) => [el.dataset.key, parseInt(el.value, 10)]));
        const weights = normaliseWeights(raw);
        for (const key of WEIGHT_KEYS) {
            document.getElementById(`v-${key}`).textContent = `${Math.round(weights[key] * 100)}%`;
            const el = document.getElementById(`w-${key}`);
            el.style.setProperty('--fill', `${el.value}%`);
        }
        return weights;
    }

    for (const el of inputs) {
        el.addEventListener('input', () => onInput(readWeights()));
        el.addEventListener('change', () => onCommit(readWeights()));
    }
    return readWeights();
}

export function markSelectedRow(name) {
    for (const [rowName, row] of leaderboardRows) row.classList.toggle('is-selected', rowName === name);
}

export function initDetailCard({ onClose }) {
    document.getElementById('detail-back').addEventListener('click', onClose);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !document.getElementById('detail').hidden) onClose();
    });
}

// opening=true replays the bar fill from zero; otherwise bars ease to new values.
export function showDetail(b, rank, { opening = false } = {}) {
    const card = document.getElementById('detail');
    document.getElementById('detail-rank').textContent = `#${rank + 1} · score ${b.overall_score.toFixed(1)} / 100`;
    document.getElementById('detail-name').textContent = b.borough;
    document.getElementById('detail-source').innerHTML = sourceTagHtml(b);
    document.getElementById('detail-housing').innerHTML = b.housing_apps > 0
        ? `🏗️ <strong>${b.housing_approval_rate}%</strong> planning approval · ${b.housing_apps.toLocaleString()} applications`
        : '🏗️ No planning data';

    const bars = [...card.querySelectorAll('.bar')];
    for (const bar of bars) {
        const value = b[bar.dataset.key];
        bar.querySelector('strong').textContent = `${value}/10`;
        if (opening) bar.querySelector('.bar-fill').style.width = '0%';
    }
    card.hidden = false;
    if (opening) card.getBoundingClientRect();
    requestAnimationFrame(() => {
        for (const bar of bars) bar.querySelector('.bar-fill').style.width = `${b[bar.dataset.key] * 10}%`;
    });
}

export function hideDetail() {
    document.getElementById('detail').hidden = true;
}

export function setSyncStatus(state, text) {
    const el = document.getElementById('sync-status');
    el.dataset.state = state;
    el.textContent = text;
}
