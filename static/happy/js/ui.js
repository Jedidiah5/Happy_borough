import { FACTORS, WEIGHT_KEYS, normaliseWeights } from './scoring.js';
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

function escapeHtml(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
}

function infoIconHtml(f) {
    if (!f.source) return '';
    return ` <span class="info-wrap">
        <button type="button" class="info-icon" aria-label="Data source for ${escapeHtml(f.label)}" aria-expanded="false">ⓘ</button>
        <span class="info-tip" role="tooltip">${escapeHtml(f.source)}</span>
    </span>`;
}

function buildSliders() {
    document.getElementById('sliders').innerHTML = FACTORS.map((f) => `
        <div class="slider-group">
            <div class="slider-row"><span>${f.icon} ${escapeHtml(f.label)}${f.note ? ` <small>${escapeHtml(f.note)}</small>` : ''}${infoIconHtml(f)}</span><strong id="v-${f.key}"></strong></div>
            <input type="range" id="w-${f.key}" data-key="${f.key}" min="0" max="100" value="${f.defaultWeight}" aria-label="${escapeHtml(f.label)} weight">
        </div>`).join('');

    for (const btn of document.querySelectorAll('#sliders .info-icon')) {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const wrap = btn.closest('.info-wrap');
            const isOpen = wrap.classList.contains('is-open');
            for (const other of document.querySelectorAll('#sliders .info-wrap.is-open')) {
                other.classList.remove('is-open');
                other.querySelector('.info-icon').setAttribute('aria-expanded', 'false');
            }
            wrap.classList.toggle('is-open', !isOpen);
            btn.setAttribute('aria-expanded', String(!isOpen));
        });
    }
    document.addEventListener('click', () => {
        for (const wrap of document.querySelectorAll('#sliders .info-wrap.is-open')) {
            wrap.classList.remove('is-open');
            wrap.querySelector('.info-icon').setAttribute('aria-expanded', 'false');
        }
    });
}

function buildDetailBars() {
    document.getElementById('detail-bars').innerHTML = FACTORS.map((f) => `
        <div class="bar" data-key="${f.key}"><span>${f.icon} ${escapeHtml(f.short || f.label)}</span><div class="bar-track"><div class="bar-fill"></div></div><strong></strong></div>`).join('');
}

export function initSliders({ onInput, onCommit }) {
    buildSliders();
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
    buildDetailBars();
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
    document.getElementById('detail-extras').innerHTML = detailCardExtras(b);

    const factorByKey = new Map(FACTORS.map((f) => [f.key, f]));
    const bars = [...card.querySelectorAll('.bar')];
    const values = bars.map((bar) => Number(factorByKey.get(bar.dataset.key).value(b)) || 0);
    bars.forEach((bar, i) => {
        bar.querySelector('strong').textContent = `${+values[i].toFixed(1)}/10`;
        if (opening) bar.querySelector('.bar-fill').style.width = '0%';
    });
    card.hidden = false;
    document.body.classList.add('has-detail');
    if (opening) card.getBoundingClientRect();
    requestAnimationFrame(() => {
        bars.forEach((bar, i) => { bar.querySelector('.bar-fill').style.width = `${Math.min(values[i], 10) * 10}%`; });
    });
}

const estimatedTag = (flag) => (flag ? ' <span class="dx-est" title="Estimated">est.</span>' : '');

export function detailCardExtras(b) {
    const cells = [];
    const rent = b.rent;
    if (rent && rent.typical_monthly) {
        cells.push(`<div class="dx-cell"><span class="dx-label">💷 Typical rent${estimatedTag(rent.estimated)}</span>
            <strong class="dx-value">£${Math.round(rent.typical_monthly).toLocaleString()}<small>/mo</small></strong>
            ${rent.rent_1bed ? `<span class="dx-sub">1-bed £${Math.round(rent.rent_1bed).toLocaleString()} · 2-bed £${Math.round(rent.rent_2bed || 0).toLocaleString()}</span>` : ''}</div>`);
    }
    if (b.green_space_pct != null) {
        cells.push(`<div class="dx-cell"><span class="dx-label">🌳 Green space</span>
            <strong class="dx-value">${b.green_space_pct}<small>% of land</small></strong>
            ${b.green_space_sites ? `<span class="dx-sub">${b.green_space_sites.toLocaleString()} mapped parks &amp; open spaces</span>` : ''}</div>`);
    }
    const wb = b.wellbeing;
    if (wb) {
        const trend = wb.life_satisfaction_trend;
        const arrow = typeof trend === 'number' ? (trend > 0 ? '▲' : trend < 0 ? '▼' : '■') : '';
        const trendCls = typeof trend === 'number' ? (trend > 0 ? 'dx-up' : trend < 0 ? 'dx-down' : '') : '';
        cells.push(`<div class="dx-cell"><span class="dx-label">😊 Life satisfaction${estimatedTag(wb.estimated)}</span>
            <strong class="dx-value">${wb.life_satisfaction ?? '–'}<small>/10</small>${arrow ? ` <span class="dx-trend ${trendCls}">${arrow}</span>` : ''}</strong>
            <span class="dx-sub">Anxiety ${wb.anxiety ?? '–'} · Worthwhile ${wb.worthwhile ?? '–'}${wb.latest_year ? ` · ${escapeHtml(wb.latest_year)}` : ''}</span></div>`);
    }
    const imd = b.imd;
    if (imd && imd.overall_decile) {
        const chips = [
            ['Income', imd.income_decile], ['Health', imd.health_decile], ['Education', imd.education_decile],
            ['Crime', imd.crime_decile], ['Environment', imd.living_environment_decile],
        ].filter(([, v]) => v != null)
            .map(([name, v]) => `<span class="dx-chip" style="--d:${v}">${name} <b>${+Number(v).toFixed(1)}</b></span>`).join('');
        cells.push(`<div class="dx-cell dx-wide"><span class="dx-label">📊 Deprivation deciles <small>(10 = least deprived)</small></span>
            <strong class="dx-value">${+Number(imd.overall_decile).toFixed(1)}<small>/10 overall</small></strong>
            <div class="dx-chips">${chips}</div></div>`);
    }
    return cells.length ? `<div class="dx-grid">${cells.join('')}</div>` : '';
}

export function hideDetail() {
    document.getElementById('detail').hidden = true;
    document.body.classList.remove('has-detail');
}

export function setSyncStatus(state, text) {
    const el = document.getElementById('sync-status');
    el.dataset.state = state;
    el.textContent = text;
}
