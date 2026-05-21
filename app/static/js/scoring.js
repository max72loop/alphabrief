// ── Freemium daily counter ─────────────────────────────────────────────────
var FREE_DAILY_LIMIT = 5;

function _todayStr() { return new Date().toISOString().slice(0, 10); }

function getAnalysesUsed() {
    if (localStorage.getItem('ab_analyses_day') !== _todayStr()) return 0;
    return parseInt(localStorage.getItem('ab_analyses_count') || '0', 10);
}

function addAnalysesUsed(n) {
    var today = _todayStr();
    var current = localStorage.getItem('ab_analyses_day') === today
        ? parseInt(localStorage.getItem('ab_analyses_count') || '0', 10) : 0;
    localStorage.setItem('ab_analyses_day', today);
    localStorage.setItem('ab_analyses_count', current + (n || 1));
}

window.AB = { getAnalysesUsed: getAnalysesUsed, addAnalysesUsed: addAnalysesUsed, FREE_DAILY_LIMIT: FREE_DAILY_LIMIT };

document.addEventListener('DOMContentLoaded', function () {

    // ── Scoring overlay ─────────────────────────────────────────────────────
    var SCORING_MSGS = [
        'Récupération des données de marché…',
        'Analyse des fondamentaux…',
        'Calcul des indicateurs techniques…',
        'Analyse IA en cours…',
        'Calcul du score final…',
    ];

    function showScoringOverlay() {
        var overlay = document.getElementById('scoring-overlay');
        var msgEl   = document.getElementById('scoring-msg');
        if (!overlay || !msgEl) return;

        overlay.classList.add('visible');
        var i = 0;
        msgEl.textContent = SCORING_MSGS[0];

        setInterval(function () {
            i = (i + 1) % SCORING_MSGS.length;
            msgEl.classList.add('fading');
            setTimeout(function () {
                msgEl.textContent = SCORING_MSGS[i];
                msgEl.classList.remove('fading');
            }, 200);
        }, 3500);
    }

    // Overlay pour score unique + invalidation cache (pas de vérification freemium)
    document.querySelectorAll(
        'form[action*="/scoring/score"], form[action*="/cache/invalidate"]'
    ).forEach(function (form) {
        form.addEventListener('submit', showScoringOverlay);
    });

    // ── Score unique : loading state + tracking freemium ────────────────────
    document.querySelectorAll('form[action*="/scoring/score"]').forEach(function (form) {
        form.addEventListener('submit', function () {
            addAnalysesUsed(1);
            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Scoring…';
                btn.classList.add('btn-loading');
            }
        });
    });

    // ── Batch score : vérification freemium + overlay + loading state ────────
    document.querySelectorAll('form[action*="/scoring/batch"]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            var tickerCount = parseInt(form.dataset.tickerCount || '0', 10);
            if (!tickerCount) {
                tickerCount = document.querySelectorAll('tbody tr:not(.row-hidden)').length || 1;
            }

            var used = getAnalysesUsed();
            var remaining = FREE_DAILY_LIMIT - used;

            if (remaining <= 0) {
                e.preventDefault();
                if (confirm('Limite atteinte : ' + FREE_DAILY_LIMIT + ' analyses gratuites utilisées aujourd\'hui.\n\nVoir les offres Premium ?')) {
                    window.location.href = '/#pricing';
                }
                return;
            }

            if (tickerCount > remaining) {
                var ok = confirm(
                    'Il vous reste ' + remaining + ' analyse(s) gratuite(s) aujourd\'hui, ' +
                    'mais votre liste contient ' + tickerCount + ' ticker(s).\n\n' +
                    'Continuer quand même ?'
                );
                if (!ok) {
                    e.preventDefault();
                    return;
                }
            }

            addAnalysesUsed(tickerCount);
            showScoringOverlay();

            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Scoring en cours…';
                btn.classList.add('btn-loading');
            }
        });
    });

    // ── Flash messages auto-dismiss ─────────────────────────────────────────
    function dismissFlash(el) {
        el.classList.add('hiding');
        setTimeout(function () { el.remove(); }, 320);
    }

    document.querySelectorAll('.flash-close').forEach(function (btn) {
        btn.addEventListener('click', function () {
            dismissFlash(btn.closest('.flash'));
        });
    });

    document.querySelectorAll('.flash[data-autohide="true"]').forEach(function (el) {
        setTimeout(function () { dismissFlash(el); }, 4000);
    });

    // ── Gauge arc animation ─────────────────────────────────────────────────
    document.querySelectorAll('.gauge-arc').forEach(function (arc) {
        var target = parseFloat(arc.dataset.offset);
        setTimeout(function () {
            arc.style.strokeDashoffset = target;
        }, 120);
    });

    // ── Importance bars animation ───────────────────────────────────────────
    document.querySelectorAll('.imp-bar').forEach(function (bar, i) {
        var w = bar.dataset.width;
        setTimeout(function () {
            bar.style.width = w;
        }, 200 + i * 60);
    });

});
