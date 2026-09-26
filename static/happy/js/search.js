// Postcode/address/borough search bar. Resolves a free-text query to one of
// the 33 tracked boroughs via /api/geocode, then hands the matched borough
// name to the caller -- this module owns none of the borough metrics itself,
// since the caller (main.js) already has the full, real per-borough data
// from /api/rankings and can show it via the existing selection flow.
function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function initSearch({ onResolved, onClear, isReady } = {}) {
    const form = document.getElementById('search-form');
    const input = document.getElementById('search-input');
    const clearBtn = document.getElementById('search-clear');
    const feedback = document.getElementById('search-feedback');

    let requestId = 0;

    function setFeedback(state, html) {
        feedback.hidden = !html;
        feedback.className = state ? `search-feedback is-${state}` : 'search-feedback';
        feedback.innerHTML = html || '';
    }

    async function executeSearch(query) {
        const q = query.trim();
        if (!q) {
            resetSearch();
            return;
        }
        if (isReady && !isReady()) {
            setFeedback('error', 'Still loading borough data — try again in a moment.');
            return;
        }

        const thisRequest = ++requestId;
        clearBtn.hidden = false;
        setFeedback('searching', `Searching for "<b>${escapeHtml(q)}</b>"…`);

        let result;
        try {
            const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
            result = await res.json();
        } catch (err) {
            if (thisRequest !== requestId) return;
            setFeedback('error', `Search failed: ${escapeHtml(err.message)}`);
            return;
        }
        if (thisRequest !== requestId) return;

        if (!result.found) {
            setFeedback('error', result.message || 'No matching London borough, postcode or address found.');
            return;
        }

        const distText = result.distance_km > 0 ? ` (~${result.distance_km}km away)` : '';
        setFeedback('success', `📍 <b>${escapeHtml(result.matched_name)}</b> → <b>${escapeHtml(result.borough)}</b>${distText}`);
        onResolved && onResolved(result);
    }

    function resetSearch() {
        requestId++;
        input.value = '';
        clearBtn.hidden = true;
        setFeedback(null, '');
        onClear && onClear();
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        executeSearch(input.value);
    });

    input.addEventListener('input', () => {
        clearBtn.hidden = !input.value.trim();
    });

    clearBtn.addEventListener('click', resetSearch);

    return { resetSearch };
}
