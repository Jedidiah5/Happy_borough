const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

export function prefersReducedMotion() {
    return reducedMotionQuery.matches;
}

export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

const activeTweens = new Set();

// Tweens are advanced by the render loop (see tickTweens) so they share one rAF.
export function animate({ duration, delay = 0, ease = easeOutCubic, onUpdate, onComplete }) {
    const reduced = prefersReducedMotion();
    const tween = {
        start: performance.now() + (reduced ? 0 : delay),
        duration: reduced ? 0 : duration,
        ease,
        onUpdate,
        onComplete,
    };
    activeTweens.add(tween);
    return () => activeTweens.delete(tween);
}

export function tickTweens(now) {
    for (const tween of activeTweens) {
        if (now < tween.start) continue;
        const progress = tween.duration <= 0 ? 1 : Math.min(1, (now - tween.start) / tween.duration);
        tween.onUpdate(tween.ease(progress));
        if (progress >= 1) {
            activeTweens.delete(tween);
            if (tween.onComplete) tween.onComplete();
        }
    }
}
