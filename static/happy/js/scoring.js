// One entry per /api/rankings weight. `value(b)` returns the 0-10 metric the
// server multiplies by that weight, so FACTORS drives sliders, bars and scoring.
export const FACTORS = [
    { key: 'safety', param: 'w_safety', icon: '🛡️', label: 'Safety', note: 'live police data', defaultWeight: 20, value: (b) => b.safety_score },
    { key: 'green', param: 'w_green', icon: '🌳', label: 'Parks & green space', short: 'Green space', defaultWeight: 20, value: (b) => b.green_space },
    { key: 'transport', param: 'w_transport', icon: '🚆', label: 'Transport access', short: 'Transport', defaultWeight: 15, value: (b) => b.transport_score },
    { key: 'happiness', param: 'w_happiness', icon: '😊', label: 'ONS wellbeing', short: 'Wellbeing', defaultWeight: 15, value: (b) => b.ons_happiness },
    { key: 'barriers', param: 'w_barriers', icon: '🏘️', label: 'Housing access', note: 'IMD barriers decile', short: 'Housing access', defaultWeight: 15, value: (b) => b.imd?.housing_barriers_decile ?? 0 },
    { key: 'affordability', param: 'w_affordability', icon: '💷', label: 'Affordable rent', short: 'Affordability', defaultWeight: 15, value: (b) => b.affordability_score ?? 0 },
];

export const WEIGHT_KEYS = FACTORS.map((f) => f.key);

export function normaliseWeights(raw) {
    const total = WEIGHT_KEYS.reduce((sum, key) => sum + raw[key], 0) || 1;
    return Object.fromEntries(WEIGHT_KEYS.map((key) => [key, raw[key] / total]));
}

// Client copy of the /api/rankings formula in happiness_server.py:
//   score = sum(metric * 10 * weight) over all six factors, rounded to 1dp.
// Keep in sync; main.js warns in the console if the two drift apart.
export function computeScore(borough, weights) {
    const score = FACTORS.reduce((sum, f) => sum + f.value(borough) * 10 * weights[f.key], 0);
    return Math.round(score * 10) / 10;
}

export function rankBoroughs(boroughs, weights) {
    return boroughs
        .map((b) => ({ ...b, overall_score: computeScore(b, weights) }))
        .sort((a, b) => b.overall_score - a.overall_score);
}
