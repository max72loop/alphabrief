# AlphaBrief

Suivi de patrimoine personnel, mono-utilisateur, sans intention commerciale.
Voir ses investissements répartis sur plusieurs supports au même endroit,
garder des notes éditables sur les sociétés suivies, et se faire relancer
chaque semaine pour saisir les nouveaux chiffres.

Ce n'est plus un screener vendu en SaaS. Toute la logique de facturation a été
retirée au lot 1 (2026-07-31).

## Stack

- **Backend** : Python (lib de scoring importée par le daemon — voir « Runtime »)
- **Base** : **Postgres 16 local**, base `alphabrief`, sur le VPS
- **Interface** : les cartes AlphaBrief du cockpit Pixel Office (API 127.0.0.1:4300)
- **Data** : FMP (de nouveau servi, plan limité aux cotations US — voir « Gotchas ») puis yfinance en complément
- **LLM** : Haiku 4.5 via OpenRouter (`OPENROUTER_API_KEY`) — résumé, moats, catalyseurs, risques de la fiche ; Sonnet 5 pour Sage

**Supabase a été abandonné le 2026-08-01.** Un service managé multi-utilisateur
n'apportait rien à un produit mono-utilisateur et coûtait une clé partagée,
une couche RLS entière et une étape manuelle pour appliquer chaque migration.
La reprise est faite : 2367 lignes. Les exports JSON de reprise ont été
détruits le 2026-09-04 avec le reste du SaaS — ils contenaient un e-mail en
clair, un `plan: premium` et un `stripe_customer_id`. Le Postgres local et ses
dumps quotidiens (`make db-backup`, cron 03:20) sont la seule source à sauver.

### Connexion — il n'y a pas de secret

`core/storage/db.py` se connecte par socket Unix sous l'identité de
l'utilisateur système (`dbname=alphabrief`). Ni URL, ni clé, ni mot de passe,
ni variable d'environnement obligatoire. Rien à stocker, donc rien à faire
fuiter et rien à faire tourner. Surcharge possible par `ALPHABRIEF_DSN` —
c'est ce qui permet aux tests de viser la miroir.

Postgres n'écoute que `localhost` (vérifié). L'isolation vient du réseau et de
la session applicative, pas d'une couche de policies : **il n'y a aucune RLS
et c'est délibéré**, voir le §7 de `migrations/2026_07_31_patrimoine_schema.sql`.

## Runtime

Ce repo est une **librairie** (`core/`, `utils/`) consommée par deux runtimes :

```
/root/agents/alphabrief/main.py   ← daemon de prod (PM2 "alphabrief")
    APScheduler : cycle éco 6h · scoring+rapport 7h · sage 8h ·
                  health /30min · cache cleanup 3h · heartbeat /30s
    Importe core.generator, core.storage.writer, core.providers.events_yf,
    core.scoring.bands, core.bitcoin.cycle_detector
    Exporte data/score_bands.json au démarrage (l'API Pixel Office le sert)
    ⚠ Couplé à l'écosystème Alfred (alfred.shared.{config,logger,telegram,
      redis_client,heartbeat}) — dépendance à DOCUMENTER, pas à casser :
      le rappel hebdomadaire du lot 4 s'appuie dessus.

core/cli.py   ← outil local (python -m core.cli analyze/run-all/status)
```

Le dépôt distant du daemon (`alphabrief-agent`) n'existe pas sur GitHub. Son
historique est poussé sur `refs/heads/daemon-runtime` du repo `alphabrief`,
en attendant mieux.

## Modèle de données (lot 1)

`supports` · `positions` · `snapshots` · `flux` · `societes`

**Un support n'est pas un compte, c'est une poche homogène.** Un compte mixte
se déclare en plusieurs supports (Revolut → « Revolut Actions » + « Revolut
Crypto »). C'est ce qui permet à `classe_dominante` d'être NOT NULL et à la
répartition par classe de n'avoir aucun trou.

**Non-double-comptage.** `snapshots.niveau` vaut `support` ou `position`, et
une contrainte CHECK interdit qu'il diverge des FK. Le total d'un support est
le snapshot de niveau `support`. Le détail par position ne s'y additionne
jamais : il se **réconcilie** contre lui, et l'écart est une information, pas
une erreur.

**Toute somme passe par `v_patrimoine_total`.** Aucune agrégation ad hoc dans
le code applicatif — c'est ce qui empêche un futur écran de réinventer un
`SUM(valeur_eur)` qui mélangerait les deux niveaux.

**Exception unique et cadrée : le total live** (`pixel-office-api/routes/patrimoine.js
::totalLive`, 2026-09-03, demandé par Max). `v_patrimoine_total` ne bouge qu'à la
saisie ; il était resté figé au 24 août pendant que le détail par position changeait
tous les jours, ce qui se lisait comme une panne. Le total live suit les cotations
et respecte la même règle de non-double-comptage : **pour un support donné, SOIT la
somme de ses positions, SOIT son snapshot de niveau `support`, jamais les deux.**
Une position sans cotation (le cash, un ticker inconnu de yfinance) retombe sur sa
dernière valeur saisie et alimente `estime_eur`, affiché comme « dont N € non coté »
— sans ce repli, une poche non cotée disparaîtrait du total. Si aucune ligne n'est
réellement cotée, la route renvoie `null` et l'écran retombe sur la saisie : mieux
vaut ça qu'une copie des saisies déguisée en temps réel.

## Règles de travail

### Suppression — critère mécanique, jamais l'intuition

Aucune suppression sur la foi d'un nom de fichier ou de dossier. Avant tout
`rm` / `git rm` : **grep des imports entrants sur chaque fichier concerné**, et
résultat du grep documenté dans la PR.

```bash
# imports par alias ET par chemin relatif — les deux, sinon on en rate
grep -rn "components/landing/Gauge\|from ['\"]\./landing/Gauge" src/
```

Origine de la règle : au lot 1, `components/landing/Gauge.tsx` avait été
flaggé « supprimer » parce qu'il vivait dans `landing/`. C'était le design
system, importé par 14 fichiers hors landing. Un inventaire bâti sur les noms
de dossiers ment.

### Frontière d'autonomie

**Totale sur la base miroir. Nulle sur la base `alphabrief`.**

Commits en local : libres. Sur la miroir : appliquer, casser, recréer, rejouer
depuis zéro autant de fois que nécessaire, sans rien demander.

Demandent un feu vert explicite de Max :

- **push sur `main`** — le daemon tourne sur le code du VPS ; un push reste un
  geste de versioning, mais tout `git clean` dans ce repo est proscrit (des
  modules atteints par le daemon y ont déjà traîné non versionnés)
- **toute écriture sur la base `alphabrief`** dès qu'elle portera des montants
  réels. Le fait que la base soit maintenant locale ne dissout pas ce veto :
  il portait sur les données de Max, pas sur l'hébergeur. `make db-apply` est
  idempotent et ne supprime rien, mais il reste soumis à cette règle.
- **modification de variables d'environnement**
- **suppression de table**

### Les deux bases — `alphabrief` et `alphabrief_mirror`

`alphabrief` est la vraie. `alphabrief_mirror` est **jetable, sans aucune
donnée réelle, jamais**. Les deux sont construites depuis **les mêmes fichiers**
(`db/schema.sql` puis `migrations/2026_07_31_patrimoine_schema.sql`) : la
miroir est une répétition fidèle, plus une approximation écrite à la main.

```
make db-apply    # applique le schema sur la VRAIE base (idempotent, ne detruit rien)
make db-reset    # recree la miroir et rejoue le schema DEUX fois
make db-check    # rejoue les assertions seules
make db-diff     # compare le DDL reel de la vraie base a celui du depot
make db-backup   # pg_dump horodate vers /root/backups (cron 03:20 UTC, retention 30j)
```

`db-reset` refuse de tourner si `MIRROR_DB` vaut la vraie base : la cible fait
un `DROP DATABASE`, une faute de frappe ne doit pas pouvoir détruire le
patrimoine.

**Une migration ne part sur `alphabrief` qu'après être passée au vert sur la
miroir, avec la sortie collée dans la livraison.** Le double passage vérifie
l'idempotence mécaniquement, pas par relecture.

`make db-diff` remplace l'ancien `db-drift`, qui interrogeait la spec OpenAPI
de PostgREST. Celui-ci compare deux `pg_dump` : il voit les contraintes UNIQUE
hors PK, les FK, les CHECK, les index, les triggers **et les séquences** — tous
les angles morts de l'introspection HTTP. Il a trouvé une vraie dérive à sa
première exécution (contrainte `ticker_events_ticker_date_kind_key` absente de
la vraie base), qui aurait fait échouer l'upsert d'events au scoring suivant.

### Mémoire externe (mempalace)

**Aucun montant réel, aucun solde, aucune valorisation ne doit atterrir dans un
tiroir mempalace ni dans le journal.** Les décisions, les raisons et le code :
oui. Les chiffres du patrimoine de Max : jamais. Cela vaut aussi pour les
extraits de sortie SQL et les dumps collés dans une livraison.

Vérifier le graphe à chaque checkpoint : un fait périmé qui reste `current`
sera relu comme vrai plus tard. Invalider (`kg_invalidate`) plutôt que
d'empiler une contradiction.

### Vérification

- Les calculs financiers doivent être couverts par des tests à cas connus
  vérifiés à la main.
- Comparer avant/après plutôt qu'affirmer : mesurer la baseline (`git stash`,
  worktree sur le commit précédent) avant de dire « aucune régression ».
- Ne jamais commiter les `.env` / `.env.local`.

## Contraintes produit

- Mono-utilisateur, mais **auth obligatoire** : aucune donnée patrimoniale
  lisible sans session. RLS fermée, `authenticated` uniquement.
- Devise de référence EUR. `valeur_eur` et `montant_eur` sont des colonnes
  générées : la conversion n'est jamais saisie à la main.
- **Aucun appel API payant en boucle** : cache agressif, refresh quotidien
  suffit pour du patrimoine long terme.
- L'écran de saisie hebdomadaire doit tenir en moins de 3 minutes. S'il est
  pénible, il ne sera pas utilisé — c'est le critère de survie du produit.

## Gotchas

- **FMP est revenu, limité aux cotations US (constaté le 2026-10-27).** `profile`,
  `treasury-rates`, `analyst-estimates`, comptes trimestriels répondent ; un symbole
  hors US (1211.HK, IWDA.AS…) répond **402 « Premium Query Parameter »**. Ce 402-là
  ne concerne QUE ce symbole : `fmp_client` le mémorise par symbole
  (`_premium_symbols`) sans ouvrir le coupe-circuit — avant le 27/10, le premier
  ticker étranger coupait FMP pour toute la watchlist pendant 1 h. Verrouillé par
  `test_402_premium_ne_coupe_que_ce_symbole`. Le paragraphe suivant (FMP mort) est
  l'historique de septembre ; le coupe-circuit reste utile si le plan retombe.
- **FCF = `freeCashFlow` de FMP (2026-10-27).** L'ancien calcul OCF +
  `investmentsInPropertyPlantAndEquipment` prenait le flux d'exploitation pour du FCF
  quand FMP laisse ce champ à 0 (IREN : +2,10 Md$ lus pour −2,23 Md$ réels).
  Tests : `tests/core/providers/test_fundamentals_fcf.py`.
- **Devise de publication ≠ devise de cotation (corrigé le 2026-10-27).** Les deux
  chemins de `fundamentals_yf` calculent `fcf_absolute ÷ capitalisation` sans
  conversion : TSM 44,3 % au lieu de 1,4 % (TWD/USD), ASR 67,4 % au lieu de 3,6 %
  (MXN/USD), RIO.AX (USD/AUD), titres HK (CNY/HKD). `generate_card` recalcule
  `valuation.fcf_yield_ttm` dans la devise de la capitalisation AVANT la notation
  (valeur d'origine dans `fcf_yield_ttm_brut`, détail dans `rendement.conversion_fcf`).
  TSM 65 → 61, ASR 56 → 54 (Fort → Modéré). **Reste à vérifier** : les ratios
  calculés par FMP sur EV (EV/EBITDA, EV/Sales) pour les mêmes cotations.
- **Prime de rendement et dilution par an (2026-10-27).** `core/scoring/prime.py`
  (prime = FCF yield [+ croissance CA consensus si ≥ 10 %, plafonnée 15] − 10 ans
  US ; banques/assureurs sur l'earnings yield ; vert ≥ +2, rouge < −1, n/a si FCF
  ≤ 0) — **EN OMBRE** : `card.rendement`, `ombre_json.prime`,
  `ticker_scores.rendement` (migration `2026_10_27_rendement.sql`), jamais dans la
  note. `core/scoring/dilution.py` (actions diluées trimestrielles, 1 an / 3 ans
  annualisés, chute > 25 %/trimestre = événement sans bonus, fenêtre d'avant IPO
  + 90 j écartée, pire des deux fenêtres) → `financials.dilution_an`, qui entre
  dans la note (pilier Qualité, pénalité > 3 %/an, bonus léger 60 sur rachats).
  `ENGINE_VERSION = "2026-10-27"`. Données : `core/providers/rendement.py`, cache
  `rendement` 24 h, ≈ 2 appels FMP par ticker et par jour + 1 pour le taux.
- **FMP est mort, yfinance est la source réelle** (constaté le 2026-09-02 — historique, voir ci-dessus).
  Tous les endpoints répondent `429 "Limit Reach . Please upgrade your plan"`,
  `profile` compris. Ce n'est pas une rafale mais le quota du plan, donc
  permanent : le backoff 5/15/45 ne pouvait jamais aboutir et brûlait 65 s par
  endpoint, soit ~7,5 min par ticker. `fmp_client` distingue désormais les deux
  causes de 429 (`_looks_like_plan_limit`) et ouvre un coupe-circuit
  process-wide sur la seconde, avec un cooldown d'1 h. `plan_exhausted()`
  expose l'état, `reset_plan_breaker()` le referme après un changement de plan.
  Le health check sonde FMP et publie `plan_exhausted` — volontairement **pas**
  dans `issues`, qui notifierait Telegram toutes les 30 min pour un état stable.
  **Depuis le 2026-09-08, FMP répond aussi `402 Payment Required`**, et c'est ce
  code-là qu'il sert au scoring de 5 h. Le coupe-circuit ne regardait que le
  429 : le 402 tombait dans le `except RequestException` générique, donc dans le
  backoff complet — exactement ce que ce coupe-circuit existe pour éviter. Le
  22/09, les 402 couraient de 05:00:02 à 05:43:26 sans que le circuit ne s'ouvre
  une seule fois : **39 appels d'endpoint × 65 s ≈ 42 min de `time.sleep` par
  matin**, soit la quasi-totalité de la fenêtre de scoring (05:00 → 05:44,
  stable sur cinq jours). Corrigé le 2026-09-22 : un 402 ouvre le circuit
  immédiatement, comme un 429 « Limit Reach ». La leçon vaut au-delà de FMP —
  **un coupe-circuit câblé sur un code de statut meurt en silence le jour où le
  fournisseur en change**, et rien ne le dit puisque le repli, lui, marche.
  Verrouillé par `tests/core/providers/test_fmp_client.py::test_http_402_ouvre_le_coupe_circuit_sans_backoff`,
  qui vérifie qu'une seule requête part.
- **Un fournisseur qui tombe se dit UNE fois (2026-09-22).** `plan_exhausted`
  reste hors de `issues` — un état stable répété toutes les 30 min n'apprend
  qu'à ignorer les health checks. Mais la BASCULE se signale, à l'aller comme au
  retour : `main.py::_signaler_bascule_fournisseur` compare l'état à
  `alphabrief:fournisseur:<nom>` en Redis (FMP, yfinance) et n'envoie une ligne
  Telegram qu'au changement. **La première observation est muette** : un
  redéploiement n'annonce pas une panne déjà connue. C'est ce qui manquait le
  08/09 — l'état n'avait pas changé (FMP était déjà mort), mais sa *signature*
  si, et personne ne l'a su pendant quatorze jours.
- **`fundamentals_yf` complète TOUS les tickers, sans condition.** Le nom trompe :
  ce module interroge FMP d'abord, puis `_complete_from_yf` comble tout champ
  resté vide. La complétion ne se limite plus aux tickers internationaux, et
  n'est plus conditionnée à un seuil (`n_valid < 5`) qui était de surcroît
  compté *après* que l'ownership yfinance ait déjà rempli 3 champs. Elle ne
  remplace jamais une valeur existante, donc FMP garde autorité s'il revient.
  Avant ce changement, 14 champs manquaient sur 29 à 32 cartes sur 39 —
  dont `revenue_cagr_3y` (0,45 du pilier Croissance à lui seul) et
  `fcf_yield_ttm` (le composant le plus lourd de Valeur). Confiance moyenne
  passée de 68 à 88. `paper_mvp.py` est sur yfinance pour la même raison.
- **`price_identity` suit exactement le même contrat depuis le 2026-09-02.**
  C'était le dernier chemin encore branché sur FMP seul : 224 des 232 cartes
  en cache n'avaient ni nom, ni secteur, ni capitalisation, ni prix (18 champs
  vides sur 23), les 8 rescapées étant les tickers internationaux, seuls à
  bénéficier du repli. `fetch_identity_and_market` part maintenant direct sur
  yfinance quand `plan_exhausted()` est vrai, et complète sinon les champs
  vides via `_complete_from_yf` sans écraser ce qu'FMP a donné. Comme pour les
  fondamentaux : **après un changement ici, purger `data/cache/*_identity.json`**,
  sinon le correctif reste invisible 6 h. `Ticker.info` est mémoïsé par process
  (`clear_info_cache()`) — trois chemins le demandaient pour un même ticker.
- **Le portefeuille et le moteur ne parlent pas le même symbole.** `positions.actif`
  porte la cotation où Max détient réellement le titre ; la watchlist porte celle
  qu'on analyse. Pour quatre sociétés ce n'est pas le même : `BYDDY`→`1211.HK`,
  `GOOGL`→`GOOG`, `ASURB.MX`→`ASR`, `RIO`→`RIO.AX`. Le cockpit résout la note par
  correspondance EXACTE (`scoreByTicker[position.actif]`), donc ces quatre lignes
  n'affichaient AUCUNE notation alors que le score existait sous un autre nom.
  Les équivalences vivent dans `core/scoring/listings.py`, exportées en JSON au
  boot du daemon (comme le barème) et lues par l'API. **Ne jamais résoudre en
  ajoutant le symbole détenu à la watchlist** : on obtiendrait deux verdicts pour
  une même société — c'est exactement ce qu'a produit l'ancienne ligne `GOOGL`
  (63 « Modéré ») restée à côté de `GOOG` (61 « Exceptionnel »).
- **Il y a DEUX stores de scores, et ils ne servent pas les mêmes écrans.**
  Le daemon écrit SQLite `mytrader.db::scores_history` (`_save_score`) — c'est ce
  que lit l'API Pixel Office, donc le cockpit. `core/cli.py` écrit, lui, le
  Postgres `ticker_scores` + `score_history` (`core/storage/writer.py`) — c'est ce
  que lit la carte Ticker du cockpit (`alphabrief_card.js`). Un
  `python -m core.cli analyze TICKER` ne fait donc
  PAS apparaître la note dans le cockpit, et réciproquement. Pour alimenter les
  deux, passer par le chemin du daemon (`_save_card` + `_save_score`) en plus.
- **Il n'y a plus qu'UN score, et il ne parle que de la société.** Le facteur
  `0.8 + 0.2*confiance/100` a été retiré de `core/generator.py` le 2026-09-07.
  Il rabotait la note selon la DISPONIBILITÉ DES DONNÉES, si bien que le même
  nombre répondait à deux questions — « cette société vaut-elle quelque chose »
  et « qu'en sait-on » — sans que le lecteur puisse les démêler. Il ne pouvait
  que baisser, jamais relever, et comme les bandes ne font que 4 à 6 points de
  large il déplaçait **4 cartes sur 39 d'une bande entière** au 2026-09-07
  (NU 61→58 et HOOD 62→59 perdaient « Exceptionnel »).
  Son histoire dit assez qu'il n'a jamais trouvé son réglage : plancher relevé
  de 0,5 à 0,8 (FIX I1), puis étiquette déplacée d'avant à après le facteur
  (FIX I4) parce que la carte affichait le nombre d'après et le mot d'avant.
  **Le garde-fou a changé de place, il n'a pas disparu** : sous
  `bands.CONFIDENCE_FLOOR` (60), `bands.band_for()` rend la bande
  « Données insuffisantes » au lieu d'un verdict. Le seuil n'est pas arbitraire :
  la distribution des confiances coupe d'elle-même là (4 cartes à 51-59, la
  suivante à 74, médiane 93,5). Toujours verrouillé par
  `tests/test_scoring_smoke.py::test_label_matches_displayed_score`.
- **Le moteur note sous un secteur TRADUIT, pas sous le libellé yfinance
  (2026-09-23).** Ses tables (`potential._SECTOR_*`, `momentum._SECTOR_ETFS`)
  sont en GICS, yfinance parle Morningstar : « Healthcare », « Consumer
  Cyclical », « Consumer Defensive », « Basic Materials » n'y figuraient pas,
  donc bornes par défaut et momentum contre le SPY pour ces secteurs.
  `core/scoring/secteur.py::secteur_moteur` traduit (via `normalize_sector`),
  et **un secteur `manuel` de `societes` gagne** (CHYM, néobanque rangée en
  Technology). `generate_card` pose `identity.sector_note`, que lisent
  `compute_potential_score` et le momentum relatif ; `identity.sector` reste
  le libellé brut. Piège : « Financials » et « Financial Services » sont DEUX
  barèmes (bancaire / fintech) ; le GICS les confond, la traduction renvoie
  donc vers « Financial Services », celui qu'ont toujours eu les financières.
  Impact mesuré sur les 40 cartes du 23/09 : 8 bougent de ±1-2, une bande
  change (1211.HK 49 → 50, Faible → Modéré).
- **Un bénéfice exceptionnel n'entre plus dans la Valeur (2026-09-23).**
  `potential.benefice_exceptionnel(pe, forward_pe, roe)` : P/E TTM positif et
  (forward > 2 × TTM, ou ROE < 0). P/E TTM et PEG (y compris le pegRatio Yahoo)
  sortent du pilier, le forward P/E reste sans comparaison au TTM. Même règle
  dans `importance.py`, qui affiche « Bénéfice exceptionnel probable » au lieu
  de « P/E attractif ». CHYM : Valeur 65 → 33, note 60 → 59.
  Tests : `tests/core/scoring/test_secteur_et_benefice.py`.
- **`score_band` et `confidence` sont persistés — l'API ne redérive plus rien.**
  `alphabrief_card.js` recalculait la bande depuis le seul score. Depuis qu'une
  carte peut être « Données insuffisantes » — un état qu'aucun seuil de score ne
  permet de retrouver — cela affichait le ton et le blurb de « Faible » à côté du
  libellé « Données insuffisantes ». Deux colonnes ajoutées à `ticker_scores`, et
  `bands.py` exporte `insufficient_band` à part (elle n'a pas de borne).
- **Un composant sans donnée n'entre plus dans un pilier.** Qualité et Risque
  appliquaient déjà cette règle (FIX I5) ; **Valeur ne l'appliquait pas** — six
  de ses neuf composants étaient inconditionnels, donc une société dont on
  ignorait tout de la valorisation recevait Valeur = 50 bâti sur six 50 fantômes,
  sur le pilier le plus lourd des fondamentaux (32 %). Au 2026-09-07 : 8 cartes
  sur 39 sans FCF yield, 8 sans EV/EBITDA, 5 sans PEG. `beta` et `debt` étaient
  les deux derniers inconditionnels de Risque (45 % du pilier). Corrigé le
  2026-09-07 — chaque pilier a désormais un repli neutre si sa liste finit vide.
  Corollaire : `_normalize_dividend_yield` rend `None` sur valeur aberrante et
  non plus `0.0`, sinon une donnée corrompue se déguisait en « ne verse pas de
  dividende », qui est maintenant un fait qui compte.
- **`roic` n'a JAMAIS contenu du ROIC — c'était du ROA.** Les deux chemins du
  provider l'alimentaient avec le rendement des actifs (`returnOnAssetsTTM` côté
  FMP, `returnOnAssets` côté yfinance) pendant que `compute_roic_score` le notait
  sur une échelle ROIC (« > 20 % : wide moat probable »). Le ROA étant très
  inférieur au ROIC dès qu'il y a du levier ou des actifs lourds, le composant
  démolissait exactement les compounders de qualité — KO stockait 13,3, soit
  environ la moitié de son ROIC réel. Renommé `roa` / `compute_roa_score` le
  2026-09-07, paliers redescendus (médiane S&P non financière ≈ 5-7 %), et
  neutralisé pour les banques et assureurs via `is_financial` comme
  `ebit_margin`. **Après ce changement il FAUT purger `data/cache/*_fundamentals.json`**
  (fait) : les payloads en cache portent encore l'ancienne clef.
- **La confiance doit rester le miroir exact du moteur.** `confidence.py:FEATURES`
  avait dérivé : ~17 entrées lues par `compute_potential_score` n'y figuraient
  pas (roa, net_margin, eps_growth, current_ratio, insider/institutional,
  accruals, altman_z, short_interest, gm_trend, price_to_ocf, sma_50, macd_line,
  momentum_1m/3m/6m, tous les relative_momentum_*), si bien qu'une carte pouvait
  annoncer « confiance 96 » en ignorant un tiers de ce que le moteur lisait. Anodin
  tant que la confiance n'était qu'un rabot ; déterminant maintenant qu'elle
  commande l'étiquette. Verrouillé dans les deux sens par
  `tests/core/scoring/test_confidence_couvre_le_moteur.py`, qui lit l'AST de
  `compute_potential_score` — ne pas « réparer » ce test en y ajoutant une
  exception, ajouter l'entrée à `FEATURES`.
- **Le barème de notation a une source de vérité unique** : `core/scoring/bands.py`.
  Tout ce qui étiquette, colore ou alerte sur un score importe d'ici — rien ne
  redéfinit ses propres bornes. Avant, le même score portait quatre verdicts
  contradictoires (generator 80/65/50/35/20, ancien front Vercel 55/48/42/35, alerte
  Telegram 60, Pixel Office 60/45) et deux des seuils étaient inatteignables.
  Les bornes sont des percentiles d'un échantillon **transversal** (173 sociétés :
  S&P 500 stratifié par secteur + watchlist), pas d'un historique : les 2795
  scores sur 90 jours étaient 37 tickers mesurés 75 fois. `--check` compare aux
  percentiles observés, `--export` régénère `data/score_bands.json` que sert
  l'API Pixel Office. La recalibration reste une décision manuelle.
- **La calibration du barème est un job, plus un fichier oublié.** `scripts/backtest.py`
  existait mais n'avait tourné qu'une fois, le 2026-05-24 ; sa sortie s'affichait
  bien dans le cockpit (`BacktestBlock`), en perf ABSOLUE — donc illisible : dans
  un marché qui monte, toutes les tranches paraissent bonnes. Réécrit le
  2026-09-07 : perf **en excès de l'ETF du secteur** (le même que le momentum
  relatif, `_SECTOR_ETFS`), **fenêtres disjointes** (l'ancienne version comptait
  2748 observations tirées de 47 tickers, soit un N indépendant gonflé d'environ
  20×), **intervalle bootstrap tiré sur les tickers** et non sur les observations,
  et découpage sur les **bandes publiées** plutôt que des tranches arbitraires.
  Le chiffre à retenir est l'écart bande haute − bande basse. Job mensuel
  `run_backtest` (1er à 4h), `--backtest` en manuel, alerte Telegram si l'écart
  est négatif. **`scores_history` porte désormais `price` et les trois
  sous-scores** (SQLite et Postgres) : sans eux, aucune analyse par pilier n'était
  possible et le backtest re-téléchargeait tout yfinance à chaque exécution.
  Premier résultat honnête (2026-09-07, 52 tickers, 262 observations) : écart
  −0,75 pt à 30 j et −11,4 pts à 90 j — mais la bande haute ne compte que 5
  observations à 90 j, et seule « Fort » a un intervalle entièrement sous zéro.
  **Lire l'intervalle avant de conclure** ; l'écran affiche « pas encore
  mesurable » sous 20 observations sur la bande haute.
  **Mesure à J+7 (2026-09-22, 53 tickers, 8 mois, fenêtres disjointes)** — même
  règle que le verdict Sage du 19/10, pour que les deux se lisent avec la même
  règle. Écart haut − bas : **−0,33 pt** (n_haut 68 / n_bas 302). Quatre bandes
  sur cinq ont un intervalle qui enjambe zéro, donc pas de signal ; la seule
  exception est **« Exceptionnel » à −0,54 % [−1,36 ; −0,07]**, intervalle
  entièrement sous zéro sur 68 observations et 16 tickers. À prendre pour ce que
  c'est : cinq bandes × trois fenêtres testées, une borne haute à −0,07 est
  fragile, ce n'est pas une découverte. Ce qui tient, c'est le négatif : **à
  l'échelle où l'on juge Sage, l'échelle de notes ne trie pas.** Reproduire sans
  rien écrire — `backtest.py::main` écrase `backtest_latest.json`, que le
  cockpit affiche ; appeler `run([7, 30, 90])` et `afficher()` directement.
- **Méthode de notation : mesurer avant de changer (2026-09-28).** Trois pièces :
  · **La moitié prix (T + M) ne trie rien, et le momentum 12-1 non plus.**
    `scripts/backtest_prix.py` rejoue le VRAI moteur sur des indicateurs
    recalculés à chaque fin de mois, 2016 → 2026, S&P 500 actuel (402 titres
    téléchargés sur 500), excès sur l'ETF du secteur. Corrélation de rang
    moyenne : T+M −0,005 (t −0,3) à 21 j, +0,005 (t +0,2) à 63 j ; 12-1 relatif
    −0,007 / −0,003. Aucun |t| ≥ 1. Le remplacement prévu (12-1) n'a donc PAS
    été branché. Biais du survivant assumé (il gonfle le momentum, et même
    ainsi rien ne sort). Cours en cache : `data/cache/backtest_prix_cours.pkl`.
  · **Score en ombre** `core/scoring/ombre.py` : une métrique par idée (ROA,
    1/P/E forward, CAGR CA 3 a, dette nette/EBITDA) classée en percentile DANS
    son secteur contre `data/ombre_reference.json` (`scripts/reference_ombre.py`,
    S&P 500 stratifié 18/secteur seed 42), + le 12-1 relatif brut. Calculé par
    le daemon à chaque scoring, écrit dans `scores_history.ombre_json`, jamais
    affiché. `_ombre()` avale toute exception : il ne doit jamais bloquer le
    score de prod. La référence est chargée UNE fois par process — la
    reconstruire impose un redémarrage du daemon.
  · **`scores_history.engine_version`** = `potential.ENGINE_VERSION`, à changer
    à chaque modification qui déplace des notes. `scripts/backtest.py` publie
    désormais `correlations` (IC de rang par date, moyenné, t) pour le score,
    les sous-scores, chaque pilier et l'ombre, et `engine_versions`. Règle de
    décision : un signal sans IC positif à t ≥ 2 ne mérite aucun poids. Les
    piliers ne sont historisés que depuis le 07/09 : pas de verdict avant
    plusieurs mois.
- **Série 3 (2026-09-18) — ce qui est vivant depuis :**
  · `flux` (apports/retraits) s'écrit depuis la carte de compte du cockpit ;
    la ligne « Compte » des horizons est **hors apports nets** (voir
    `pixel-office-api/routes/patrimoine.js::horizonsCompte`). La courbe
    `nav_daily` reste brute, apports compris — c'est voulu.
  · Une position se **clôture** (`ouverte=false`) et s'**ajuste** depuis la
    ligne (`⋯`) : `POST /positions/:id/snapshot` accepte `base_eur`, qui
    réécrit la `valeur` du snapshot d'ouverture = la base du P&L. Pas de PRU,
    juste une base que Max tient à jour. Toute écriture invalide le cache de
    prix live.
  · **Sage lit `societes.these`** (`sage_advisor._theses`, suffixe « thèse de
    Max : « … » » sur les lignes détenues et les candidats) et sa règle dit
    que la thèse prime : il ne propose une vente qu'en nommant ce qui la
    contredit. Sans thèse, chiffres seuls.
  · Le Radar du cockpit montre la watchlist entière groupée par bande
    (`SuiviBlock`, `alphaShared.scoreBandFor(score, confiance)` — sous
    `confidence_floor`, « Données insuffisantes », jamais « Faible »).
- **Une alerte = un franchissement de bande (2026-09-18).** `_check_alert`
  (daemon) compare `bands.band_for(score, confiance)` d'aujourd'hui à celle du
  dernier relevé (`_get_latest_row`, avec sous-scores) : types `BAND_UP` /
  `BAND_DOWN`, message « Fort → Modéré · momentum −12 » (le pilier qui a le plus
  bougé), **sans le ticker**. Plus de seuil local : `alert_score_delta` et
  `strong_buy_score` ont disparu de `DEFAULT_CONFIG`. « Données insuffisantes »
  n'est pas une bande, rien ne se déclenche en y entrant/sortant. Rejeu du
  18/09 : 2 à 10 franchissements/jour sur 43 titres (contre 199 STRONG_BUY
  accumulés avant). Le rapport de 7h liste « 🔔 Changements de bande », mes
  titres d'abord, et cite `societes.these` sous un titre détenu qui DESCEND
  (`_alert_lines`). Les anciens types en base restent affichables tels quels.
- **La couche IA des fiches a tourné pour la première fois le 2026-09-18.**
  `llm_enricher.py` visait DeepSeek avec une clé qui n'a jamais existé →
  `None` silencieux, 0 fiche sur 40 avec un résumé. Désormais OpenRouter +
  Haiku 4.5, même client que Sage, prompt en français, `segments` /
  `top_competitors` retirés du contrat. Sortie validée (`_parse`) : invalide →
  `None` et **pas de cache** (48 h, `utils/cache.py::SECTION_TTL["llm"]`).
  Persisté dans `ticker_scores.catalysts` / `key_risks` (JSONB, ajoutés après
  `pillars`, écrits seulement si non vides), servis par `/api/alphabrief/card`
  (`a_surveiller`), affichés dans la fiche avec les `moat_tags`. Les fiches
  se remplissent au fil des scorings (cache vide → un appel par ticker le
  premier matin). Piège vu à `make db-diff` : `nav_daily` (créée le 11/09 par
  l'API Pixel Office) n'est PAS dans `db/schema.sql` — dérive préexistante,
  la miroir ne la connaît pas.
- **Couche « phase de cycle » (2026-09-19) — une grille de lecture, jamais un
  signal.** `core/cycle/mapping.py` porte la table secteur GICS → phase
  (Stovall / Fidelity), constante VERSIONNÉE et exportée en `data/cycle_mapping.json`
  au boot du daemon, comme le barème et les équivalences ; l'API ne redéclare
  jamais la table. `societes.secteur_gics` (+ `secteur_source`,
  `secteur_updated_at`, migration `2026_09_19_cycle.sql`) est posé par
  `core/cycle/secteurs.enregistrer` depuis `writer.write_score`, sous le ticker
  NOTÉ, et **jamais écrasé** (une correction manuelle → `secteur_source='manuel'`
  tient). La source réelle est celle de la fiche — FMP étant mort, c'est
  yfinance (taxonomie Morningstar normalisée en GICS par `normalize_sector`,
  qui rend `None` sur un libellé inconnu, jamais une devinette). La phase est
  **DÉCLARÉE** par Max (`cycle_phase_declarations`, journal en ajout seul, datée),
  pas lue du détecteur de `core/bitcoin/cycle_detector.py` : celui-ci vote sur
  des prix, les entrées macro du modèle (10 a − 3 m, ISM, chômage, CPI core)
  ne sont pas branchées. Mêmes clés de phase des deux côtés (`recovery`,
  `expansion`, `slowdown`, `recession`), libellé « Fin de cycle » pour `slowdown`.
  Côté cockpit : `positions_dashboard.py` porte `classe` et `secteur_gics` par
  ligne (liste plate, `alpha_probe.py` d'Alfred en dépend), l'API croise dans
  `lib/alphabrief_cycle.js` (pure, `validate_cycle_lecture.js`), route
  `/api/alphabrief/cycle/lecture` + `PUT …/cycle/phase`, composant
  `CycleLecture.jsx` sous la bande de phase. La limite empirique (Molchanov
  2024 : 0,16 %/mois ; Stangl 2009 : −2,3 %/an) est affichée en clair, et
  l'Expansion est marquée « peu informatif ». Tests :
  `ALPHABRIEF_DSN="dbname=alphabrief_mirror" pytest tests/core/cycle`.
- **Catégories de Peter Lynch (2026-10-04) — grille de lecture, le score n'en
  dépend pas.** `core/lynch/categories.py` (pur, `VERSION`, seuils, libellés,
  « ce que Lynch surveille », export `data/lynch_categories.json` au boot du
  daemon) et `core/lynch/store.py` (`societes.lynch_categorie/_source/_regle/
  _updated_at`, migration `2026_10_04_lynch.sql`, appliquée). Règle, premier cas
  qui s'applique : perte nette ET CA 3 a < 10 % → redressement ; secteur Energy/
  Materials/Industrials → cyclique ; CA 3 a ≥ 20 % → croissance rapide ; ≥ 5 % →
  valeur solide ; sinon croissance lente ; CA inconnu → non classée. « Valeur
  d'actifs » : jamais proposée, posée à la main. **Contrat inverse du secteur** :
  la règle est RECALCULÉE à chaque `write_score` (la croissance bouge), mais une
  ligne `lynch_source='manuel'` n'est jamais touchée ; `declarer(t, None)` la rend
  aux règles. La croissance du CA remplace celle des bénéfices (`earningsGrowth`
  trimestriel, trop bruité) — la règle affichée le dit. Écrite par Pixel Office
  via `python -m core.lynch.store --set T CLE | --reset T`. `positions_dashboard.py`
  porte `lynch_categorie` par ligne (répartition du patrimoine). **Sage : prêt,
  ÉTEINT** (`SAGE_LYNCH = False`) jusqu'au verdict v2 du 19/10 ; l'allumer passe
  le prompt en v3. Tests : `pytest tests/core/lynch tests/core/providers/test_sage_lynch.py`
  (+ `ALPHABRIEF_DSN="dbname=alphabrief_mirror"` pour les écritures).
- **`societes.these` est vivante depuis le 2026-09-17** — la table dormait
  depuis le schéma du 31/07. Lue par `GET /api/alphabrief/card` (champs `these`,
  `these_updated_at`), écrite par `PUT /api/alphabrief/societe` (Pixel Office),
  saisie dans la fiche Ticker du cockpit, sauvée sans bouton. **Clé = ticker
  NOTÉ** (`listings.resolve`, GOOGL→GOOG) : une thèse par société, jamais une
  par cotation — même règle que le score. `notes` et `statut` restent inutilisés.
- **`ticker_events` a enfin un lecteur (2026-09-17).** Synchronisée à chaque
  scoring depuis des mois, lue par personne. Désormais : section « 📅 Résultats
  cette semaine » du rapport de 7h (`_upcoming_earnings`, fenêtre 7 j, détenus
  d'abord, absente si vide, aussi dans `report_*.json::earnings_week`) et
  `prochains_resultats` sur chaque ligne de `/api/patrimoine/positions` (le
  cockpit ne l'affiche que sous 14 j). Les dates yfinance au-delà du prochain
  trimestre sont souvent estimées — les fenêtres courtes sont là pour ça.
- **Résultats trimestriels de mes sociétés (2026-09-29).** Table
  `resultats_trimestriels` (migration `2026_09_29_resultats_trimestriels.sql`,
  appliquée), une ligne par publication, clé = ticker NOTÉ. Remplie par
  `core/providers/trimestres_yf.py::sync_detenus` à la fin du scoring du daemon
  (actions des positions ouvertes seulement), lue par l'onglet « Résultats » de
  Pixel Office (`/api/alphabrief/resultats`). Verdict = BPA publié contre
  consensus, `SEUIL_VERDICT_PCT` = ±2 %, calculé en Python et stocké — l'API
  et l'écran ne le recalculent jamais. Lecture IA (Haiku, même client que
  `llm_enricher`) écrite UNE fois par publication récente (≤ 100 j), avec la
  thèse de `societes`. Pièges : les lignes À VENIR d'un ticker sont supprimées
  puis réécrites à chaque synchro (les dates yfinance lointaines bougent) ;
  yfinance ne garde que ~5 trimestres de CA, d'où l'upsert en COALESCE sur
  `ca`/`fin_trimestre`/`ca_un_an_avant`/`resultat_net` et le CA « un an avant »
  complété depuis la table elle-même ; un consensus de CA à 0 (émetteur
  semestriel, RIO.AX) = inconnu ; CS.PA et RIO.AX n'ont pas de trimestres chez
  yfinance (semestriels) ; un BPA attendu proche de 0 donne des surprises
  > 100 % que l'écran remplace par « publié contre attendu ». Tests :
  `ALPHABRIEF_DSN="dbname=alphabrief_mirror" pytest tests/core/providers/test_trimestres_yf.py`
  (le test d'écriture se saute hors miroir).
- **`courbe` de `/api/patrimoine` = `nav_daily`, plus les dates de saisie
  (2026-09-17).** L'ancienne série listait les saisies (3 points en un mois) et
  n'était affichée nulle part. Elle sert maintenant la sparkline sous le total
  dans Comptes : 90 photos au plus + le point live du jour. `variation_eur`
  reste l'écart entre deux SAISIES (requête dédiée), ne pas le faire dériver.
- **Paper trading (TOP10) retiré le 2026-08-22** — jobs daemon, route API et
  section du digest hebdo supprimés. `paper_mvp.py` reste dans le repo : sa
  fonction `_fetch_quote` est réutilisée par le script de prix live des
  positions patrimoine (`/root/agents/alphabrief/scripts/positions_dashboard.py`).
  Ses fonctions de rebalance (`run_weekly_rebalance`, `run_daily_nav`) ne sont
  plus appelées par personne — ne pas les relancer sans en reparler à Max.
- **`alerts` et `portfolio_holdings` n'existent pas**, et ne sont pas recréées
  dans le schéma local. La fonctionnalité d'alertes n'a jamais tourné. Le seul
  code qui les interrogeait était le frontend Next.js, supprimé avec le SaaS le
  2026-09-04 : on ne recrée pas une table pour faire taire du code mort.
- **Les séquences sont invisibles à l'introspection OpenAPI.** C'est le piège
  qui a failli coûter cher à la reprise : les `id` sont des identités, et
  insérer les lignes reprises avec leur `id` ne fait pas avancer le compteur.
  Sans le `setval` de `db/load_export.py`, la première écriture du daemon
  serait repartie à `id = 1` — violation de clé primaire des mois plus tard,
  sans rapport apparent avec la migration. `db/schema.sql` utilise
  `GENERATED BY DEFAULT` (et non `ALWAYS`) précisément pour que la reprise
  puisse fournir les `id` explicites sans `OVERRIDING SYSTEM VALUE`.
- Le cache des cartes est dans `data/cache/*.json` et SQLite (`data/mytrader.db`)
  — certains fichiers portent encore l'ancien nom « MyTrader ». **Le TTL n'est pas
  global** : il est par section dans `utils/cache.py::SECTION_TTL` — fundamentals 6 h,
  identity 6 h, momentum 2 h, technicals 1 h, llm 48 h. Conséquence pratique :
  après un changement du pipeline de fondamentaux, purger `*_fundamentals.json`,
  sinon le correctif reste invisible 6 h (`_fetch_fundamentals` réutilise tout
  payload ayant ≥ 3 valeurs non nulles).
- L'app Flask v1 est archivée : tag `archive/flask-v1`, branche `archive/flask`.
  Restauration : `git checkout archive/flask-v1 -- app/`.
- `core/paper_portfolio/` est gelé (36 `NotImplementedError`). Sur ses 154 tests,
  **113 échouent et 41 passent** — c'est la baseline, pas une régression ; un
  `pytest tests/` qui affiche ces deux nombres est un run sain. Ses seuils morts
  `SCORE_THRESHOLD_TOP = 80` / `BOTTOM = 30` ont été retirés le 2026-09-02 (80
  était inatteignable : le moteur plafonne à 68). Une reprise du module doit
  lire `core.scoring.bands`, pas redéclarer des bornes.
- `core/bitcoin/` contient deux choses de statut différent. `cycle_detector.py`
  **est sur le chemin critique depuis le 2026-09-02** : le daemon le rafraîchit
  à 6 h (`refresh_economic_cycle`) et Pixel Office affiche la phase en tête de
  l'écran AlphaBrief. Il était resté orphelin six mois après la suppression de
  l'app Flask, cache figé au 2026-02-28, sans que rien ne le signale — d'où
  l'âge du relevé désormais affiché et le passage en « détection en retard »
  au-delà de 48 h. `btc_buy_signal_analyzer.py` reste, lui, hors du chemin
  critique, en lecture seule.
