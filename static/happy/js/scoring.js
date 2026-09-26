export const WEIGHT_KEYS = ['safety', 'green', 'transport', 'happiness'];

// Slider values (any scale) -> weights that sum to 1, as sent to /api/rankings.
export function normaliseWeights(raw) {
    const total = WEIGHT_KEYS.reduce((sum, key) => sum + raw[key], 0) || 1;
    return Object.fromEntries(WEIGHT_KEYS.map((key) => [key, raw[key] / total]));
}

/*
 * computeScore: client-side copy of the /api/rankings scoring formula in
 * happiness_server.py. Keep the two in sync: if the team changes the server
 * formula, change it here too. main.js warns in the console when the server
 * and this function disagree by more than 0.1.
 *
 *   overall_score = safety_score    * 10 * w_safety
 *                 + green_space     * 10 * w_green
 *                 + transport_score * 10 * w_transport
 *                 + ons_happiness   * 10 * w_happiness      (rounded to 1 dp)
 */
export function computeScore(borough, weights) {
    const score =
        borough.safety_score * 10 * weights.safety +
        borough.green_space * 10 * weights.green +
        borough.transport_score * 10 * weights.transport +
        borough.ons_happiness * 10 * weights.happiness;
    return Math.round(score * 10) / 10;
}

// Returns a new array sorted like the server: overall_score descending.
export function rankBoroughs(boroughs, weights) {
    return boroughs
        .map((b) => ({ ...b, overall_score: computeScore(b, weights) }))
        .sort((a, b) => b.overall_score - a.overall_score);
}
