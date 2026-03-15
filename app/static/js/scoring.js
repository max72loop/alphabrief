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

    document.querySelectorAll(
        'form[action*="/scoring/score"], form[action*="/scoring/batch"], form[action*="/cache/invalidate"]'
    ).forEach(function (form) {
        form.addEventListener('submit', showScoringOverlay);
    });

    // ── Loading state on score buttons (keep existing behaviour) ────────────
    document.querySelectorAll('form[action*="/scoring/score"]').forEach(function (form) {
        form.addEventListener('submit', function () {
            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Scoring…';
                btn.classList.add('btn-loading');
            }
        });
    });

    document.querySelectorAll('form[action*="/scoring/batch"]').forEach(function (form) {
        form.addEventListener('submit', function () {
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
