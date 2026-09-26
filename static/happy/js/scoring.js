// One entry per /api/rankings weight. `value(b)` returns the 0-10 metric the
// server multiplies by that weight, so FACTORS drives sliders, bars and scoring.
export const FACTORS = [
    {
        key: 'safety', param: 'w_safety', icon: '🛡️', label: 'Safety', note: 'live police data', defaultWeight: 20, value: (b) => b.safety_score,
        source: 'Live UK Police API (data.police.uk): crime count within ~1 mile of the borough centroid, cached 1hr. Falls back to a hand-curated benchmark (12 boroughs) or the IMD 2025 Crime domain decile if the live call fails or is slow.',
    },
    {
        key: 'green', param: 'w_green', icon: '🌳', label: 'Parks & green space', short: 'Green space', defaultWeight: 20, value: (b) => b.green_space,
        source: 'OS Open Greenspace (Ordnance Survey): real per-site park/open-space polygons, summed to a % of borough land area and rescaled 0-10 (greenest = 10, least green = 0). Real data for all 33 boroughs — see build_greenspace_index.py.',
    },
    {
        key: 'transport', param: 'w_transport', icon: '🚆', label: 'Transport access', short: 'Transport', defaultWeight: 15, value: (b) => b.transport_score,
        source: 'TfL Public Transport Accessibility Level (PTAL), population-weighted from ward level to all 33 boroughs, rescaled 0-10 (least accessible = 0, most accessible = 10). City of London is such an extreme outlier that it alone sets the top of the scale — see build_transport_index.py.',
    },
    {
        key: 'happiness', param: 'w_happiness', icon: '😊', label: 'ONS wellbeing', short: 'Wellbeing', defaultWeight: 15, value: (b) => b.ons_happiness,
        source: 'ONS Personal Well-being Survey, Life Satisfaction measure, 2022-23. Real per-borough figure for 32 of 33 boroughs; City of London uses the London-wide average (its population is too small for ONS to publish one).',
    },
    {
        key: 'barriers', param: 'w_barriers', icon: '🏘️', label: 'Housing access', note: 'IMD', short: 'Housing', defaultWeight: 15, value: (b) => b.imd?.housing_barriers_decile ?? 0,
        source: 'English Indices of Deprivation 2025 (MHCLG), "Barriers to Housing & Services" domain decile, population-weighted from ~5,000 London LSOAs up to borough level. Real data for all 33 boroughs.',
    },
    {
        key: 'affordability', param: 'w_affordability', icon: '💷', label: 'Affordable rent', short: 'Affordability', defaultWeight: 15, value: (b) => b.affordability_score ?? 0,
        source: 'GLA/ONS Price Index of Private Rents, Sep 2024-Aug 2025, rescaled 0-10 relative to the cheapest/priciest borough in this dataset (not tied to income). Real data for 32 of 33 boroughs; City of London uses the London-wide average.',
    },
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
