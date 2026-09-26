import { createCityScene } from './scene.js';
import { normaliseWeights, rankBoroughs } from './scoring.js';

const DEFAULT_SLIDERS = { safety: 30, green: 30, transport: 20, happiness: 20 };

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

async function boot() {
    const city = createCityScene(document.getElementById('scene'));
    const weights = normaliseWeights(DEFAULT_SLIDERS);
    const boroughs = await fetchRankings(weights);
    city.update(rankBoroughs(boroughs, weights), { animated: false });
    document.getElementById('loading').classList.add('is-hidden');
}

boot().catch((err) => {
    console.error(err);
    document.getElementById('loading').textContent = 'Could not load rankings. Is the server running?';
});
