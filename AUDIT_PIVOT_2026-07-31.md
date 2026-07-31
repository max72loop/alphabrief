# AlphaBrief — Audit de pivot (Étape 0)

**Date** : 2026-07-31
**Objet** : passage screener SaaS → gestionnaire de patrimoine personnel mono-utilisateur.
**Statut** : audit seul. Aucune suppression, aucune modification de code.

---

## 1. Cartographie — 3 codebases, pas 1

| Emplacement | Nature | Git | Vivant ? |
|---|---|---|---|
| `/root/alphabrief` | Lib Python + migrations + CLI + **une app Flask morte** | oui, 3 fichiers modifiés non commités | partiellement |
| `/root/alphabrief-frontend` | Next.js 16 / React 19 / Tailwind 4 / Supabase SSR — **l'UI live** (Vercel) | oui, propre | oui |
| `/root/agents/alphabrief` | Daemon de prod PM2 (`main.py` + `paper_mvp.py`) | oui | oui (PM2 id 12, up 7h) |

### 1.1 `/root/alphabrief` — la lib

```
core/scoring/       potential.py (82 KB), importance.py (28 KB), confidence.py   ← le cœur Feroldi
core/features/      momentum.py, technicals.py
core/providers/     fmp_client.py, fundamentals_yf.py (19 KB), price_identity.py,
                    events_yf.py, llm_enricher.py (DeepSeek)
core/generator.py   orchestration du scoring d'un ticker
core/cli.py         python -m core.cli analyze / run-all / status
core/supabase_sink.py
core/bitcoin/       btc_buy_signal_analyzer.py (40 KB) + cycle_detector.py   ← hors périmètre patrimoine ?
core/paper_portfolio/  8 modules — TOUS GELÉS (36 NotImplementedError)
app/                Flask : 14 blueprints, 24 templates (~250 KB), onboarding.js 35 KB  ← MORT
utils/              cache.py, ticker_utils.py
data/               caches JSON (26 tickers), mytrader.db (561 KB), 4 fichiers .bak
migrations/         supabase_schema.sql, supabase_paper_portfolio_001_init.sql, 2 autres
tests/              154 tests paper_portfolio (spec sans implémentation) + 2 smoke
```

**`app/` n'est servi par personne.** Aucun process PM2 ne le lance ; dans nginx,
`/api/alphabrief` pointe vers Pixel Office (port 4300), pas vers Flask. C'est le
vestige intégral de la v1.

### 1.2 `/root/alphabrief-frontend` — l'UI live

```
src/app/dashboard/       screener filtrable (ScreenerTable.tsx 29 KB)
src/app/ticker/[symbol]/ page détail — 61 KB dans un seul fichier
src/app/watchlist/       watchlist éditoriale (Constellation, SectorMap, HeroMovers…)
src/app/portfolio/       PortfolioClient.tsx — saisie manuelle de lignes (portfolio_holdings)
src/app/compare/ marche/ historique/ search/ methode/ alerts/ settings/ login/
src/app/pricing/         ← SaaS
src/app/api/             alerts, digest (Resend), portfolio, prices, settings, watchlist,
                         webhooks/lemon-squeezy   ← SaaS
src/components/landing/  9 composants marketing (Hero, Pricing, EditorialCTA…)
src/middleware.ts        auth Supabase, protège /dashboard et /ticker/*
```

### 1.3 `/root/agents/alphabrief` — le daemon

`main.py` (27 KB), APScheduler, branché sur l'infra Alfred (`alfred.shared.*` :
config, logger, telegram, redis, heartbeat). Jobs : scoring 7h, health /30min,
cache cleanup 3h, `paper_mvp_weekly` lundi 14h UTC, `paper_mvp_nav_daily` 22h UTC,
heartbeat /30s.

---

## 2. Inventaire de la dette SaaS

Légende : **SUPPRIMER** = part au lot 1 · **ARCHIVER** = sort du repo, conservé
hors ligne · **GARDER** = reste tel quel · **REFACTOR** = le fichier survit, la
logique SaaS en sort.

### 2.1 Frontend — paiement, plan, quota

| Fichier | Lignes | Flag |
|---|---|---|
| `src/app/api/webhooks/lemon-squeezy/route.ts` | tout (4,4 KB) | **SUPPRIMER** |
| `src/app/pricing/page.tsx` | tout (7,5 KB) | **SUPPRIMER** |
| `src/components/landing/Pricing.tsx` | tout | **SUPPRIMER** |
| `src/lib/quota.ts` | tout (`FREE_DAILY_QUOTA = 5`) | **SUPPRIMER** |
| `src/app/ticker/[symbol]/page.tsx` | 217-253 (`PaywallBlock`), 1281-1298 | **REFACTOR** |
| `src/components/AppNav.tsx` | 5, 31-53, 112-119 (`getAnalysesInfo`) | **REFACTOR** |
| `src/app/dashboard/_components/AlertsAndQuota.tsx` | bloc quota 205-290 | **REFACTOR** → `Alerts.tsx` |
| `src/app/dashboard/page.tsx` | 9, 12, 168-182, 279 | **REFACTOR** |
| `src/app/settings/page.tsx` | 17, 55-70 | **REFACTOR** |
| `src/app/api/watchlist/route.ts` | 84-88 (limite gratuite) | **REFACTOR** |
| `src/app/watchlist/page.tsx` + `WatchlistClient.tsx` + `watchlist/BottomCTA.tsx` | props `isPremium` | **REFACTOR** |
| `src/components/ProfilPanel.tsx` | 110 (CTA « Passer Premium ») | **REFACTOR** |
| `.env.example` | `NEXT_PUBLIC_LEMON_CHECKOUT_URL`, `LEMON_WEBHOOK_SECRET`, `RESEND_API_KEY`, `CRON_SECRET` | **REFACTOR** |
| `package.json` | dép. `resend` | **SUPPRIMER** |

### 2.2 Frontend — marketing, onboarding, emails

| Fichier | Flag | Note |
|---|---|---|
| `src/components/landing/` (9 fichiers, ~46 KB) | **SUPPRIMER** | Hero, EditorialCTA, DailyEdition, Method, ScoreReader, TickerTape, Chrome, Gauge, Logo |
| `src/app/page.tsx` | **REFACTOR** | landing → `redirect('/dashboard')` |
| `src/app/api/digest/route.ts` (7 KB) | **ARCHIVER** | email hebdo Resend + `CRON_SECRET`, ciblé Premium |
| `src/app/settings/DigestToggle.tsx` | **SUPPRIMER** | part avec le digest |
| `src/app/methode/page.tsx` | **ARCHIVER** | page pédagogique de conversion |
| `src/components/StickyBanner.tsx` | **SUPPRIMER** | bandeau de conversion |
| `public/og.png` (452 KB), `brand-*.svg` (5) | **ARCHIVER** | assets de partage social |

### 2.3 Lib Python

| Fichier | Flag | Note |
|---|---|---|
| `MONETISATION.md`, `PRICING_STRATEGY.md` (9,7 KB) | **ARCHIVER** | hors repo |
| `CLAUDE.md` | **REFACTOR** | décrit « Freemium 5/jour », Lemon Squeezy, `profiles.is_premium` |
| `app/` entier (14 blueprints, 24 templates, ~250 KB) | **ARCHIVER** ⚠️ | code mort, cf. §3.6 |
| ↳ `app/templates/landing.html` (61 KB), `newsletter.html` | **SUPPRIMER** | |
| ↳ `app/static/js/onboarding.js` (35 KB) + `onboarding.css` (22 KB) | **SUPPRIMER** | |
| ↳ `app/static/js/scoring.js:84` (`FREE_DAILY_LIMIT`) | **SUPPRIMER** | |
| ↳ `app/templates/base.html:71` (« Passer Premium ») | **SUPPRIMER** | |
| `.env.example` : `RESEND_API_KEY` | **REFACTOR** | |
| `core/bitcoin/` (52 KB) | **À TRANCHER** | question 7 |
| `core/paper_portfolio/` (8 modules gelés) | **GARDER** | devient le bac à sable d'allocation |
| `data/*.bak` (4 fichiers, 145 KB) | **SUPPRIMER** | vestiges v1 |
| `data/mytrader.db` (561 KB) | **ARCHIVER** | ancien nom du projet |

### 2.4 Tables Supabase

| Table | Flag | Note |
|---|---|---|
| `profiles` (`is_premium`, `lemon_order_id`, `analyses_today`, `last_analysis_date`) | **REFACTOR** | ne garder qu'un row de préférences, ou supprimer |
| `portfolio_holdings` | **MIGRER puis SUPPRIMER** | saisie en dur des positions — remplacé par `transactions` dérivées (lot 1) |
| `ticker_scores` | **GARDER** | ⚠️ RLS `USING (true)` à fermer |
| `score_history` | **GARDER** | ⚠️ idem |
| `alerts` | **GARDER** | socle de l'invalidation de thèse (lot 5) |
| `ticker_events` | **GARDER** | |
| `watchlists` / `watchlist_tickers` (`user_id`) | **REFACTOR** | aplatir en mono-utilisateur |
| `paper_portfolios`, `paper_positions`, `paper_rebalances`, `paper_nav_history`, `paper_metrics`, `paper_missed_rebalances`, `paper_corporate_actions`, `paper_sofr_rates` | **GARDER + RENOMMER** `sandbox_*` | ⚠️ les 8 sont en `Public read USING (true)` |

**Tables à créer (lot 1)** : `accounts`, `transactions`, `instruments`, `fx_rates`,
`target_allocation`, `theses`, `import_batches`.

---

## 3. Points durs — à traiter avant d'écrire une ligne

### 3.1 RLS en lecture publique sur tout
`supabase_schema.sql` pose `FOR SELECT USING (true)` sur `ticker_scores`,
`score_history`, `alerts` ; la migration paper fait pareil sur les 8 tables
`paper_*` (« c'est la preuve publique »). Choix cohérent pour un screener,
inacceptable dès que ces tables portent du patrimoine réel. **Toute policy
`USING (true)` doit tomber au lot 1**, y compris sur les tables qu'on garde.

### 3.2 « Chiffré au repos » est ambigu
Supabase chiffre les disques (AES-256) par défaut, mais ça ne protège de rien
via l'API : quiconque a la `SUPABASE_SERVICE_ROLE_KEY` lit les montants en clair.
Un vrai chiffrement applicatif (pgsodium/Vault, ou côté client) interdit
d'agréger en SQL — il faudrait tout calculer en mémoire. Impact direct sur le
lot 2. → **question 5**.

### 3.3 Le paper trading à « reconvertir » n'existe pas
`core/paper_portfolio/` : 36 `NotImplementedError` répartis sur 8 modules. Le
README le dit lui-même (« FROZEN, jugé sur-dimensionné »). Ce qui tourne, c'est
`agents/alphabrief/paper_mvp.py` (13 KB), beaucoup plus simple. Les 154 tests
TDD sont une **spec sans implémentation** : utile comme cahier des charges du
bac à sable, mais il n'y a pas de code à recycler.

### 3.4 FMP est en 429 permanent
`paper_mvp.py:55` : *« yfinance, pas FMP : le plan FMP est saturé en quota
(429 permanent) »*. Le « pipeline d'ingestion FMP à garder et durcir » est donc
à moitié hors service, et la prod est déjà repassée sur yfinance — une source
non officielle. → **question 6**.

### 3.5 Aucune notion de devise
`currency` est stocké sur `ticker_scores` et n'est **jamais** utilisé pour
convertir. Il n'existe ni table de taux, ni provider FX, ni taux historique.
Tout l'axe EUR (PRU au taux historique, valorisation au taux du jour, TWR/XIRR)
est à construire de zéro, source de données comprise.

### 3.6 250 KB de Flask mort
`app/` (14 blueprints, 24 templates, `landing.html` à 61 KB) n'est lancé par
aucun process et référencé par aucun vhost. Le traîner coûte à chaque grep, à
chaque refacto. Je propose de l'archiver en bloc — pas de le migrer.

### 3.7 Le repo n'est pas propre
`/root/alphabrief` : `core/providers/fmp_client.py`, `core/providers/fundamentals_yf.py`,
`project.yml` modifiés et non commités ; `scripts/backtest.py`, `data/backtests/`,
`tests/core/providers/` non suivis. À committer ou jeter **avant** le lot 1,
sinon la PR de nettoyage sera illisible.

### 3.8 Le daemon est couplé à Alfred
`main.py` importe `alfred.shared.{config,logger,telegram,redis_client,heartbeat}`.
Le pivot ne casse pas ce couplage, mais toute modification du daemon touche
l'écosystème Alfred/Pixel Office — à garder en tête au lot 1.

---

## 4. Ce que je propose comme séquence (sous réserve des réponses)

| Lot | Contenu | Dépend de |
|---|---|---|
| **0** | Nettoyage git + archivage `app/` + fermeture des RLS publiques | Q7 |
| **1** | Purge SaaS (§2.1–2.3) + schéma `accounts`/`transactions`/`instruments`/`fx_rates` + migration `portfolio_holdings` → `transactions` | Q1, Q2, Q4, Q5 |
| **2** | Moteur de calcul pur (positions, PRU multi-devises, PnL latent/réalisé, TWR, XIRR) + tests à cas connus vérifiés à la main | Q4, Q6 |
| **3** | Dashboard + détail de ligne | lot 2 |
| **4** | Allocation cible / écart / rééquilibrage par apports + import CSV et parsers courtiers | Q1, Q3 |
| **5** | Fiscalité FR (antériorité PEA, plafond, PFU vs barème, dividendes) + journal de décision et invalidation de thèse | Q2 |

Les critères d'acceptation (« à l'euro près ») ne sont vérifiables qu'à partir
du lot 2, et seulement si la question 4 (historique complet ou reprise à date)
est tranchée.
