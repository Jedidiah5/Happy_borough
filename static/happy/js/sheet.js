// Phone layout: the controls live in a bottom sheet over the full-screen city.
// Collapsed it peeks the toolbar + search; expanded it shows priorities and the
// leaderboard. Reports how much of the screen's bottom edge is covered (by this
// sheet or the borough detail card) so the city can centre itself above it.
const SWIPE_PX = 24;

export function initSheet({ layoutQuery, onCoverChange }) {
    const sheet = document.getElementById('sheet');
    const handle = document.getElementById('sheet-handle');
    const peekContent = sheet.querySelector('.center-controls');
    const detail = document.getElementById('detail');
    const root = document.documentElement;
    let peekHeight = 0;

    const isOpen = () => document.body.classList.contains('sheet-open');

    function coveredHeight() {
        if (!layoutQuery.matches) return 0;
        if (!detail.hidden) return detail.offsetHeight;
        return isOpen() ? sheet.offsetHeight : peekHeight;
    }

    const report = () => onCoverChange(coveredHeight());

    function setOpen(open) {
        if (open === isOpen()) return;
        document.body.classList.toggle('sheet-open', open);
        handle.setAttribute('aria-expanded', String(open));
        if (!open) sheet.scrollTop = 0;
        report();
    }

    function measurePeek() {
        if (!layoutQuery.matches) return;
        peekHeight = Math.round(peekContent.offsetTop + peekContent.offsetHeight + 14);
        root.style.setProperty('--sheet-peek', `${peekHeight}px`);
    }

    // A tap on the handle toggles; a swipe on it opens/closes by direction.
    let swipeStartY = null;
    let swallowClick = false;
    handle.addEventListener('pointerdown', (e) => { swipeStartY = e.clientY; });
    handle.addEventListener('pointerup', (e) => {
        if (swipeStartY === null) return;
        const dy = e.clientY - swipeStartY;
        swipeStartY = null;
        if (Math.abs(dy) < SWIPE_PX) return;
        swallowClick = true;
        setOpen(dy < 0);
    });
    handle.addEventListener('click', () => {
        if (swallowClick) {
            swallowClick = false;
            return;
        }
        setOpen(!isOpen());
    });

    // Swipe up anywhere on the collapsed sheet opens it; swipe down from the
    // top of the expanded sheet closes it. Sliders keep their horizontal drag.
    let touchStart = null;
    sheet.addEventListener('touchstart', (e) => {
        if (e.target.closest('input[type=range], .sheet-handle')) return;
        touchStart = { y: e.touches[0].clientY, scrollTop: sheet.scrollTop };
    }, { passive: true });
    sheet.addEventListener('touchend', (e) => {
        if (!touchStart) return;
        const dy = e.changedTouches[0].clientY - touchStart.y;
        const atTop = touchStart.scrollTop <= 0;
        touchStart = null;
        if (!isOpen() && dy < -SWIPE_PX * 2) setOpen(true);
        else if (isOpen() && atTop && sheet.scrollTop <= 0 && dy > SWIPE_PX * 3) setOpen(false);
    }, { passive: true });

    const observer = new ResizeObserver(() => {
        measurePeek();
        report();
    });
    observer.observe(peekContent);
    observer.observe(sheet);
    observer.observe(detail);
    layoutQuery.addEventListener('change', () => {
        measurePeek();
        report();
    });
    measurePeek();

    return { open: () => setOpen(true), close: () => setOpen(false), report };
}
