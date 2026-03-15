/* ═══════════════════════════════════════════════════════════════
   ONBOARDING INTERACTIVE TOUR — MyTrader
   Tour produit interactif pour les nouveaux utilisateurs
═══════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    /* ── Config ─────────────────────────────────────────────── */
    const STORAGE_KEY = 'mt_tour_done_v1';
    const AUTO_SHOW_DELAY = 1200; // ms après chargement de page

    /* ── Steps definition ────────────────────────────────────── */
    const STEPS = [
        {
            id: 'welcome',
            type: 'welcome',
        },
        {
            id: 'add',
            tag: '01 — Ajoute une action',
            icon: '🔍',
            title: 'Tape le nom d\'une action <span>que tu connais</span>',
            desc: "Apple, LVMH, Tesla… tape simplement le ticker et l'algorithme l'analyse en quelques secondes. Pas besoin d'être expert.",
            bullets: [
                'AAPL pour Apple, MC.PA pour LVMH, TSLA pour Tesla',
                'L\'algo analyse 15+ critères automatiquement',
                'Résultat en moins de 10 secondes',
                '5 analyses gratuites par jour',
            ],
            visual: 'renderWatchlist',
        },
        {
            id: 'signal',
            tag: '02 — Comprends le signal',
            icon: '🚦',
            title: 'Un signal en <span>3 couleurs</span>, pas un cours en finance',
            desc: "Oublie les P/E et les MACD. Un signal simple te dit si l'action mérite ton attention aujourd'hui.",
            bullets: [
                '🟢 Acheter — momentum et fondamentaux favorables',
                '🟡 Observer — situation mixte, surveiller l\'évolution',
                '🔴 Éviter — signaux défavorables détectés',
                'Le score détaillé reste accessible si tu veux creuser',
            ],
            visual: 'renderSignal',
        },
        {
            id: 'alerts',
            tag: '03 — Active tes alertes',
            icon: '🔔',
            title: 'Sois notifié <span>quand le signal change</span>',
            desc: "L'algo surveille ta watchlist en continu. Tu reçois une alerte dès qu'une opportunité ou un risque se déclenche.",
            bullets: [
                'Signal ACHETER déclenché sur un titre suivi',
                'Variation brutale du score en quelques heures',
                'Aucune surveillance manuelle nécessaire',
                'Consulte l\'historique des alertes à tout moment',
            ],
            visual: 'renderAlerts',
        },
        {
            id: 'cta',
            type: 'cta',
        },
    ];

    /* ── State ───────────────────────────────────────────────── */
    let currentStep = 0;
    let isTransitioning = false;
    let backdrop = null;
    let contentArea = null;
    let progressFill = null;
    let stepCounter = null;
    let prevBtn = null;
    let nextBtn = null;
    let dotsContainer = null;

    /* ══════════════════════════════════════════════════════════
       HTML BUILDERS
    ══════════════════════════════════════════════════════════ */

    function buildBackdrop() {
        const el = document.createElement('div');
        el.id = 'ob-backdrop';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.setAttribute('aria-label', 'Tour de présentation MyTrader');

        el.innerHTML = `
            <div class="ob-modal" role="document">
                <!-- Barre de progression -->
                <div class="ob-progress-bar-wrap">
                    <div class="ob-progress-bar-fill" id="ob-progress-fill" style="width:0%"></div>
                </div>

                <!-- Header -->
                <div class="ob-header">
                    <div class="ob-header-left">
                        <div class="ob-logo-mark">MT</div>
                        <span class="ob-brand">MyTrader</span>
                    </div>
                    <span class="ob-step-counter" id="ob-step-counter"></span>
                    <button class="ob-close-btn" id="ob-close-btn" aria-label="Fermer le tour">✕</button>
                </div>

                <!-- Zone de contenu dynamique -->
                <div id="ob-content-area" class="ob-content"></div>

                <!-- Footer navigation -->
                <div class="ob-footer">
                    <button class="ob-nav-btn ob-btn-prev" id="ob-prev-btn" aria-label="Étape précédente">← Précédent</button>
                    <div class="ob-dots" id="ob-dots" role="tablist"></div>
                    <button class="ob-nav-btn ob-btn-next" id="ob-next-btn">Suivant →</button>
                </div>
            </div>
        `;

        document.body.appendChild(el);

        // Bind refs
        backdrop = el;
        contentArea = el.querySelector('#ob-content-area');
        progressFill = el.querySelector('#ob-progress-fill');
        stepCounter = el.querySelector('#ob-step-counter');
        prevBtn = el.querySelector('#ob-prev-btn');
        nextBtn = el.querySelector('#ob-next-btn');
        dotsContainer = el.querySelector('#ob-dots');

        // Events
        el.querySelector('#ob-close-btn').addEventListener('click', closeTour);
        prevBtn.addEventListener('click', () => navigate(-1));
        nextBtn.addEventListener('click', () => navigate(1));

        // Close on backdrop click
        el.addEventListener('click', function (e) {
            if (e.target === el) closeTour();
        });

        // Keyboard
        document.addEventListener('keydown', handleKeyboard);

        // Build dots
        buildDots();
    }

    function buildDots() {
        dotsContainer.innerHTML = '';
        STEPS.forEach((_, i) => {
            const dot = document.createElement('button');
            dot.className = 'ob-dot';
            dot.setAttribute('role', 'tab');
            dot.setAttribute('aria-label', `Étape ${i + 1}`);
            dot.addEventListener('click', () => goToStep(i));
            dotsContainer.appendChild(dot);
        });
    }

    /* ══════════════════════════════════════════════════════════
       NAVIGATION
    ══════════════════════════════════════════════════════════ */

    function navigate(dir) {
        const next = currentStep + dir;
        if (next < 0 || next >= STEPS.length || isTransitioning) return;
        goToStep(next);
    }

    function goToStep(index) {
        if (isTransitioning || index === currentStep) return;
        isTransitioning = true;

        // Fade out
        contentArea.classList.add('ob-step-exit');
        setTimeout(() => {
            contentArea.classList.remove('ob-step-exit');
            currentStep = index;
            renderStep();
            updateNav();
            contentArea.classList.add('ob-step-enter');
            setTimeout(() => {
                contentArea.classList.remove('ob-step-enter');
                isTransitioning = false;
                // Animate bars after enter
                requestAnimationFrame(animateBars);
            }, 300);
        }, 200);
    }

    function updateNav() {
        const total = STEPS.length;
        const pct = (currentStep / (total - 1)) * 100;
        progressFill.style.width = pct + '%';

        const step = STEPS[currentStep];
        const isSpecial = step.type === 'welcome' || step.type === 'cta';
        stepCounter.textContent = isSpecial ? '' : `${currentStep} / ${total - 2}`;

        prevBtn.disabled = currentStep === 0;

        if (currentStep === STEPS.length - 1) {
            nextBtn.textContent = 'Commencer gratuitement →';
            nextBtn.onclick = () => { closeTour(); window.location.href = '/watchlist'; };
        } else if (STEPS[currentStep].type === 'welcome') {
            nextBtn.textContent = 'Démarrer le tour →';
            nextBtn.onclick = () => navigate(1);
        } else {
            nextBtn.textContent = currentStep === STEPS.length - 2 ? 'Voir le résumé →' : 'Suivant →';
            nextBtn.onclick = () => navigate(1);
        }

        // Update dots
        dotsContainer.querySelectorAll('.ob-dot').forEach((dot, i) => {
            dot.classList.toggle('ob-dot-active', i === currentStep);
            dot.setAttribute('aria-selected', i === currentStep);
        });

        // Show/hide footer on welcome
        const footer = backdrop.querySelector('.ob-footer');
        footer.style.display = (step.type === 'welcome') ? 'none' : 'flex';
    }

    /* ══════════════════════════════════════════════════════════
       STEP RENDERING
    ══════════════════════════════════════════════════════════ */

    function renderStep() {
        const step = STEPS[currentStep];
        contentArea.innerHTML = '';

        if (step.type === 'welcome') {
            contentArea.style.display = 'block';
            contentArea.innerHTML = renderWelcome();
            contentArea.querySelector('#ob-start-btn').addEventListener('click', () => navigate(1));
            return;
        }

        if (step.type === 'cta') {
            contentArea.style.display = 'block';
            contentArea.innerHTML = renderCTA();
            return;
        }

        contentArea.style.display = 'grid';

        // Left col (text)
        const textCol = document.createElement('div');
        textCol.className = 'ob-text-col';
        textCol.innerHTML = `
            <div class="ob-step-tag">
                <span class="ob-step-icon">${step.icon}</span>
                ${step.tag}
            </div>
            <h2 class="ob-title">${step.title}</h2>
            <p class="ob-desc">${step.desc}</p>
            <ul class="ob-bullets">
                ${step.bullets.map(b => `<li>${b}</li>`).join('')}
            </ul>
        `;

        // Right col (visual)
        const visualCol = document.createElement('div');
        visualCol.className = 'ob-visual-col';
        visualCol.innerHTML = window['ob_' + step.visual]();

        contentArea.appendChild(textCol);
        contentArea.appendChild(visualCol);
    }

    /* ── Welcome ───────────────────────────────────────────── */
    function renderWelcome() {
        return `
            <div class="ob-welcome">
                <div class="ob-welcome-logo">MT</div>
                <h1 class="ob-welcome-title">Bienvenue sur<br><span>AlphaBrief</span></h1>
                <p class="ob-welcome-desc">
                    Analyse n'importe quelle action en 10 secondes.
                    Pas besoin d'être expert — un signal en 3 couleurs te dit tout ce que tu dois savoir.
                </p>
                <div class="ob-welcome-chips">
                    <span class="ob-welcome-chip">🟢 Acheter</span>
                    <span class="ob-welcome-chip">🟡 Observer</span>
                    <span class="ob-welcome-chip">🔴 Éviter</span>
                    <span class="ob-welcome-chip">🔔 Alertes</span>
                </div>
                <button class="ob-start-btn" id="ob-start-btn">Démarrer → (3 étapes)</button>
            </div>
        `;
    }

    /* ── CTA final ─────────────────────────────────────────── */
    function renderCTA() {
        return `
            <div class="ob-final">
                <div class="ob-final-icon">🚀</div>
                <h2 class="ob-final-title">C'est parti !</h2>
                <p class="ob-final-desc">
                    Ajoute ta première action et obtiens ton signal en quelques secondes.
                    Gratuit — 5 analyses par jour, aucune CB requise.
                </p>
                <div class="ob-final-actions">
                    <a href="/watchlist" class="ob-cta-primary" onclick="closeMTTour()">
                        Ajouter ma première action →
                    </a>
                    <button class="ob-cta-secondary" onclick="closeMTTour()">
                        Explorer d'abord
                    </button>
                </div>
            </div>
        `;
    }

    /* ══════════════════════════════════════════════════════════
       VISUAL MOCKUP RENDERERS
    ══════════════════════════════════════════════════════════ */

    window.ob_renderScoreCard = function () {
        return `
            <div class="mock-card">
                <div class="mock-card-header">
                    <span class="mock-ticker">NVDA</span>
                    <span class="mock-company">NVIDIA Corporation</span>
                    <span class="mock-exchange">NASDAQ</span>
                </div>
                <div class="mock-score-row">
                    <div class="mock-score-ring">
                        <svg width="70" height="70" viewBox="0 0 70 70">
                            <circle cx="35" cy="35" r="29" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="6"/>
                            <circle id="ob-ring-fill" cx="35" cy="35" r="29" fill="none"
                                stroke="#10b981" stroke-width="6"
                                stroke-linecap="round"
                                stroke-dasharray="182.2"
                                stroke-dashoffset="182.2"
                                style="transition: stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)"/>
                        </svg>
                        <div class="mock-score-ring-num" id="ob-score-num">0</div>
                    </div>
                    <div class="mock-score-meta">
                        <span class="mock-score-label">Score / 100</span>
                        <span class="mock-score-label">Confiance · 91%</span>
                        <span class="mock-signal">STRONG BUY</span>
                    </div>
                </div>
                <div style="font-size:0.72rem;color:rgba(248,250,252,0.35);line-height:1.55;border-top:1px solid rgba(255,255,255,0.05);padding-top:0.7rem;">
                    Leader mondial des GPU IA. Croissance des revenus data center +265% YoY.
                    Moat technologique exceptionnel avec architecture CUDA.
                </div>
            </div>
        `;
    };

    window.ob_renderBreakdown = function () {
        return `
            <div class="mock-card">
                <div class="mock-card-header">
                    <span class="mock-ticker">AAPL</span>
                    <span class="mock-company">Apple Inc.</span>
                    <span class="mock-exchange">NASDAQ</span>
                </div>
                <div class="mock-score-row">
                    <div class="mock-score-ring">
                        <svg width="70" height="70" viewBox="0 0 70 70">
                            <circle cx="35" cy="35" r="29" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="6"/>
                            <circle cx="35" cy="35" r="29" fill="none"
                                stroke="#10b981" stroke-width="6"
                                stroke-linecap="round"
                                stroke-dasharray="182.2"
                                stroke-dashoffset="43"
                                style="transition: stroke-dashoffset 1.2s"/>
                        </svg>
                        <div class="mock-score-ring-num">76</div>
                    </div>
                    <div class="mock-score-meta">
                        <span class="mock-score-label">Score / 100</span>
                        <span class="mock-score-label">Confiance · 88%</span>
                        <span class="mock-signal">BUY</span>
                    </div>
                </div>
                <div class="mock-breakdown">
                    <div class="mock-bar-row">
                        <span class="mock-bar-label">Fondamentaux</span>
                        <div class="mock-bar-track">
                            <div class="mock-bar-fill ob-bar" data-val="80" style="width:0%;background:linear-gradient(90deg,#6366f1,#818cf8)"></div>
                        </div>
                        <span class="mock-bar-val">80</span>
                    </div>
                    <div class="mock-bar-row">
                        <span class="mock-bar-label">Momentum</span>
                        <div class="mock-bar-track">
                            <div class="mock-bar-fill ob-bar" data-val="68" style="width:0%;background:linear-gradient(90deg,#7c3aed,#a78bfa)"></div>
                        </div>
                        <span class="mock-bar-val">68</span>
                    </div>
                    <div class="mock-bar-row">
                        <span class="mock-bar-label">Technicals</span>
                        <div class="mock-bar-track">
                            <div class="mock-bar-fill ob-bar" data-val="72" style="width:0%;background:linear-gradient(90deg,#10b981,#34d399)"></div>
                        </div>
                        <span class="mock-bar-val">72</span>
                    </div>
                    <div class="mock-bar-row">
                        <span class="mock-bar-label">Analyse IA</span>
                        <div class="mock-bar-track">
                            <div class="mock-bar-fill ob-bar" data-val="85" style="width:0%;background:linear-gradient(90deg,#f59e0b,#fbbf24)"></div>
                        </div>
                        <span class="mock-bar-val">85</span>
                    </div>
                </div>
            </div>
        `;
    };

    window.ob_renderWatchlist = function () {
        const items = [
            { ticker: 'NVDA', name: 'NVIDIA', score: 84, scoreClass: 'score-high', delta: '+3', deltaClass: 'delta-up' },
            { ticker: 'AAPL', name: 'Apple', score: 76, scoreClass: 'score-high', delta: '-1', deltaClass: 'delta-down' },
            { ticker: 'MSFT', name: 'Microsoft', score: 71, scoreClass: 'score-mid', delta: '+2', deltaClass: 'delta-up' },
            { ticker: 'ASML', name: 'ASML Holding', score: 68, scoreClass: 'score-mid', delta: '+5', deltaClass: 'delta-up' },
            { ticker: 'BRK.B', name: 'Berkshire', score: 52, scoreClass: 'score-low', delta: '0', deltaClass: '' },
        ];
        return `
            <div class="mock-watchlist">
                ${items.map((item, i) => `
                    <div class="mock-wl-row ${i === 0 ? 'active-row' : ''}">
                        <span class="mock-wl-ticker">${item.ticker}</span>
                        <span class="mock-wl-name">${item.name}</span>
                        <span class="mock-wl-score ${item.scoreClass}">${item.score}</span>
                        <span class="mock-wl-delta ${item.deltaClass}">${item.delta !== '0' ? item.delta : '—'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    };

    window.ob_renderScreener = function () {
        const rows = [
            { ticker: 'NVDA', sector: 'Semiconducteurs', rsi: '58', score: 84, scoreClass: 'score-high' },
            { ticker: 'AAPL', sector: 'Tech', rsi: '52', score: 76, scoreClass: 'score-high' },
            { ticker: 'MSFT', sector: 'Cloud', rsi: '61', score: 71, scoreClass: 'score-mid' },
            { ticker: 'META', sector: 'Social Media', rsi: '66', score: 69, scoreClass: 'score-mid' },
            { ticker: 'TSM', sector: 'Semiconducteurs', rsi: '49', score: 63, scoreClass: 'score-mid' },
        ];
        return `
            <div class="mock-screener">
                <div class="mock-filter-row">
                    <span class="mock-filter-chip active-chip">Score &gt; 60</span>
                    <span class="mock-filter-chip active-chip">Semicon</span>
                    <span class="mock-filter-chip">RSI 30-70</span>
                    <span class="mock-filter-chip">Momentum+</span>
                </div>
                <div class="mock-screener-table">
                    <div class="mock-screener-head">
                        <span class="mock-sh-cell" style="flex:0 0 50px">Ticker</span>
                        <span class="mock-sh-cell" style="flex:1">Secteur</span>
                        <span class="mock-sh-cell" style="flex:0 0 30px;text-align:center">RSI</span>
                        <span class="mock-sh-cell" style="flex:0 0 38px;text-align:right">Score</span>
                    </div>
                    ${rows.map(r => `
                        <div class="mock-screener-row">
                            <span class="mock-sc-ticker">${r.ticker}</span>
                            <span class="mock-sc-sector">${r.sector}</span>
                            <span class="mock-sc-rsi">${r.rsi}</span>
                            <span class="mock-sc-score">
                                <span class="mock-mini-score ${r.scoreClass}">${r.score}</span>
                            </span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    };

    window.ob_renderSignal = function () {
        const signals = [
            { ticker: 'AAPL', name: 'Apple', score: 78, cls: 'signal-acheter', label: 'Acheter' },
            { ticker: 'MSFT', name: 'Microsoft', score: 61, cls: 'signal-observer', label: 'Observer' },
            { ticker: 'META', name: 'Meta', score: 71, cls: 'signal-acheter', label: 'Acheter' },
            { ticker: 'PYPL', name: 'PayPal', score: 34, cls: 'signal-eviter', label: 'Éviter' },
            { ticker: 'UBER', name: 'Uber', score: 52, cls: 'signal-observer', label: 'Observer' },
        ];
        return `
            <div class="mock-watchlist">
                ${signals.map(s => `
                    <div class="mock-wl-row">
                        <span class="mock-wl-ticker">${s.ticker}</span>
                        <span class="mock-wl-name">${s.name}</span>
                        <span class="mock-wl-score ${s.score >= 65 ? 'score-high' : (s.score >= 40 ? 'score-mid' : 'score-low')}">${s.score}</span>
                        <span style="display:inline-flex;align-items:center;gap:0.25rem;font-size:0.65rem;font-weight:700;letter-spacing:0.07em;text-transform:uppercase;padding:0.15rem 0.45rem;border-radius:4px;${
                            s.cls === 'signal-acheter' ? 'background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3)' :
                            s.cls === 'signal-observer' ? 'background:rgba(245,158,11,0.15);color:#f59e0b;border:1px solid rgba(245,158,11,0.3)' :
                            'background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3)'
                        }">● ${s.label}</span>
                    </div>
                `).join('')}
            </div>
        `;
    };

    window.ob_renderAlerts = function () {
        return `
            <div class="mock-alerts">
                <div class="mock-alert-card alert-strong-buy">
                    <div class="mock-alert-top">
                        <span class="mock-alert-badge badge-buy">STRONG BUY</span>
                        <span class="mock-alert-ticker-name">NVDA</span>
                        <span class="mock-alert-time">il y a 2h</span>
                    </div>
                    <div class="mock-alert-text">Score 84/100 — seuil STRONG BUY franchi. RSI 58, momentum +18% sur 3 mois.</div>
                </div>
                <div class="mock-alert-card alert-jump">
                    <div class="mock-alert-top">
                        <span class="mock-alert-badge badge-jump">SCORE JUMP</span>
                        <span class="mock-alert-ticker-name">ASML</span>
                        <span class="mock-alert-time">il y a 6h</span>
                    </div>
                    <div class="mock-alert-text">Score +17 pts en 4h (51 → 68). Résultats trimestriels dépassant les attentes.</div>
                </div>
                <div class="mock-alert-card alert-drop">
                    <div class="mock-alert-top">
                        <span class="mock-alert-badge badge-drop">SCORE DROP</span>
                        <span class="mock-alert-ticker-name">PYPL</span>
                        <span class="mock-alert-time">hier</span>
                    </div>
                    <div class="mock-alert-text">Score -19 pts (72 → 53). RSI en surachat, momentum négatif sur 1 mois.</div>
                </div>
            </div>
        `;
    };

    window.ob_renderBitcoin = function () {
        return `
            <div class="mock-btc">
                <div class="mock-btc-score-row">
                    <div>
                        <div class="mock-btc-score-big" id="ob-btc-num">0</div>
                        <div class="mock-btc-label">Score BTC / 100</div>
                        <div class="mock-btc-signal">ACCUMULATE</div>
                    </div>
                </div>
                <div class="mock-btc-indicators">
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">Pi Cycle Top</span>
                        <span class="mock-btc-ind-val ind-bull">BULLISH</span>
                    </div>
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">MVRV Z-Score</span>
                        <span class="mock-btc-ind-val ind-bull">2.3 — OK</span>
                    </div>
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">S2F Model</span>
                        <span class="mock-btc-ind-val ind-neutral">NEUTRE</span>
                    </div>
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">Puell Multiple</span>
                        <span class="mock-btc-ind-val ind-bull">0.85 — BUY</span>
                    </div>
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">Fear & Greed</span>
                        <span class="mock-btc-ind-val ind-neutral">62 — GREED</span>
                    </div>
                    <div class="mock-btc-ind-row">
                        <span class="mock-btc-ind-name">Dominance BTC</span>
                        <span class="mock-btc-ind-val ind-bull">56.2% — BULL</span>
                    </div>
                </div>
            </div>
        `;
    };

    window.ob_renderCompare = function () {
        return `
            <div class="mock-compare">
                <div class="mock-compare-header">
                    <span class="mock-sh-cell" style="font-size:0.6rem;color:rgba(248,250,252,0.25);text-transform:uppercase;letter-spacing:0.06em;font-weight:700;">Métrique</span>
                    <div class="mock-cmp-col">
                        <span class="mock-cmp-ticker">NVDA</span>
                        <div class="mock-cmp-score" style="color:#10b981">84</div>
                    </div>
                    <div class="mock-cmp-col">
                        <span class="mock-cmp-ticker">AMD</span>
                        <div class="mock-cmp-score" style="color:#f59e0b">61</div>
                    </div>
                    <div class="mock-cmp-col">
                        <span class="mock-cmp-ticker">TSM</span>
                        <div class="mock-cmp-score" style="color:#f59e0b">63</div>
                    </div>
                </div>
                <div class="mock-compare-rows">
                    <div class="mock-cmp-row">
                        <span class="mock-cmp-metric">P/E Ratio</span>
                        <span class="mock-cmp-val">38.2</span>
                        <span class="mock-cmp-val">45.1</span>
                        <span class="mock-cmp-val mock-cmp-best">21.4</span>
                    </div>
                    <div class="mock-cmp-row">
                        <span class="mock-cmp-metric">Marge nette</span>
                        <span class="mock-cmp-val mock-cmp-best">55.7%</span>
                        <span class="mock-cmp-val">7.2%</span>
                        <span class="mock-cmp-val">38.9%</span>
                    </div>
                    <div class="mock-cmp-row">
                        <span class="mock-cmp-metric">ROE</span>
                        <span class="mock-cmp-val mock-cmp-best">124%</span>
                        <span class="mock-cmp-val">3.1%</span>
                        <span class="mock-cmp-val">28.4%</span>
                    </div>
                    <div class="mock-cmp-row">
                        <span class="mock-cmp-metric">Momentum 12M</span>
                        <span class="mock-cmp-val mock-cmp-best">+198%</span>
                        <span class="mock-cmp-val">+12%</span>
                        <span class="mock-cmp-val">+35%</span>
                    </div>
                    <div class="mock-cmp-row">
                        <span class="mock-cmp-metric">RSI-14</span>
                        <span class="mock-cmp-val">58</span>
                        <span class="mock-cmp-val">49</span>
                        <span class="mock-cmp-val mock-cmp-best">44</span>
                    </div>
                </div>
            </div>
        `;
    };

    /* ══════════════════════════════════════════════════════════
       ANIMATIONS POST-RENDER
    ══════════════════════════════════════════════════════════ */

    function animateBars() {
        // Animate score ring (step score)
        const ringFill = document.getElementById('ob-ring-fill');
        const scoreNum = document.getElementById('ob-score-num');
        if (ringFill && scoreNum) {
            const target = 84;
            const circumference = 182.2;
            const offset = circumference - (target / 100) * circumference;
            setTimeout(() => {
                ringFill.style.strokeDashoffset = offset;
                animateCounter(scoreNum, 0, target, 1200);
            }, 100);
        }

        // Animate breakdown bars
        document.querySelectorAll('.ob-bar').forEach(bar => {
            const val = parseInt(bar.dataset.val || '0', 10);
            setTimeout(() => { bar.style.width = val + '%'; }, 150);
        });

        // Animate BTC score counter
        const btcNum = document.getElementById('ob-btc-num');
        if (btcNum) {
            setTimeout(() => animateCounter(btcNum, 0, 67, 1200), 100);
        }
    }

    function animateCounter(el, from, to, duration) {
        const start = performance.now();
        function tick(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // ease out cubic
            const ease = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.round(from + (to - from) * ease);
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    /* ══════════════════════════════════════════════════════════
       KEYBOARD HANDLER
    ══════════════════════════════════════════════════════════ */

    function handleKeyboard(e) {
        if (!backdrop || !backdrop.classList.contains('ob-visible')) return;
        if (e.key === 'Escape') closeTour();
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') navigate(1);
        if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') navigate(-1);
    }

    /* ══════════════════════════════════════════════════════════
       OPEN / CLOSE
    ══════════════════════════════════════════════════════════ */

    function openTour(startAt) {
        if (!backdrop) buildBackdrop();
        currentStep = startAt || 0;
        renderStep();
        updateNav();
        requestAnimationFrame(() => {
            backdrop.classList.add('ob-visible');
            requestAnimationFrame(animateBars);
        });
        document.body.style.overflow = 'hidden';
    }

    function closeTour() {
        if (!backdrop) return;
        backdrop.classList.remove('ob-visible');
        document.body.style.overflow = '';
        localStorage.setItem(STORAGE_KEY, '1');
    }

    /* Public API */
    window.openMTTour = openTour;
    window.closeMTTour = closeTour;

    /* ══════════════════════════════════════════════════════════
       AUTO-SHOW (first visit)
    ══════════════════════════════════════════════════════════ */

    function maybeAutoShow() {
        // Auto-show on landing and watchlist (entry points for new users)
        const path = window.location.pathname;
        const isEntryPoint = path === '/' || path === '' || path === '/landing' ||
                             path === '/watchlist' || path === '/screener';
        if (!isEntryPoint) return;
        if (localStorage.getItem(STORAGE_KEY)) return;
        setTimeout(() => openTour(0), AUTO_SHOW_DELAY);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', maybeAutoShow);
    } else {
        maybeAutoShow();
    }

})();
