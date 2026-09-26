import { WEIGHT_KEYS, normaliseWeights } from './scoring.js';

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

export function setSyncStatus(state, text) {
    const el = document.getElementById('sync-status');
    el.dataset.state = state;
    el.textContent = text;
}
