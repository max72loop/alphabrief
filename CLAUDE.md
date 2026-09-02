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
- **Frontend** : Next.js 16 (React 19, Tailwind v4) — migration hors Vercel en cours
- **Data** : yfinance pour les fondamentaux, FMP hors service — voir « Gotchas »
- **LLM** : DeepSeek — enrichissement business snapshot

**Supabase a été abandonné le 2026-08-01.** Un service managé multi-utilisateur
n'apportait rien à un produit mono-utilisateur et coûtait une clé partagée,
une couche RLS entière et une étape manuelle pour appliquer chaque migration.
La reprise est faite : 2367 lignes, export dans
`/root/backups/alphabrief_supabase_20260801`.

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

Frontend Next.js (repo séparé alphabrief-frontend/)
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

- **push sur la branche déployée** — Vercel déploie depuis `main` du frontend,
  donc un push est une mise en production, pas un geste de versioning
- **toute écriture sur la base `alphabrief`** dès qu'elle portera des montants
  réels. Le fait que la base soit maintenant locale ne dissout pas ce veto :
  il portait sur les données de Max, pas sur l'hébergeur. `make db-apply` est
  idempotent et ne supprime rien, mais il reste soumis à cette règle.
- **modification de variables d'environnement**
- **suppression de table**
- **décommissionnement** du projet Supabase et du déploiement Vercel

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

- **FMP est mort, yfinance est la source réelle** (constaté le 2026-09-02).
  Tous les endpoints répondent `429 "Limit Reach . Please upgrade your plan"`,
  `profile` compris. Ce n'est pas une rafale mais le quota du plan, donc
  permanent : le backoff 5/15/45 ne pouvait jamais aboutir et brûlait 65 s par
  endpoint, soit ~7,5 min par ticker. `fmp_client` distingue désormais les deux
  causes de 429 (`_looks_like_plan_limit`) et ouvre un coupe-circuit
  process-wide sur la seconde, avec un cooldown d'1 h. `plan_exhausted()`
  expose l'état, `reset_plan_breaker()` le referme après un changement de plan.
  Le health check sonde FMP et publie `plan_exhausted` — volontairement **pas**
  dans `issues`, qui notifierait Telegram toutes les 30 min pour un état stable.
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
- **Le barème de notation a une source de vérité unique** : `core/scoring/bands.py`.
  Tout ce qui étiquette, colore ou alerte sur un score importe d'ici — rien ne
  redéfinit ses propres bornes. Avant, le même score portait quatre verdicts
  contradictoires (generator 80/65/50/35/20, front Vercel 55/48/42/35, alerte
  Telegram 60, Pixel Office 60/45) et deux des seuils étaient inatteignables.
  Les bornes sont des percentiles d'un échantillon **transversal** (173 sociétés :
  S&P 500 stratifié par secteur + watchlist), pas d'un historique : les 2795
  scores sur 90 jours étaient 37 tickers mesurés 75 fois. `--check` compare aux
  percentiles observés, `--export` régénère `data/score_bands.json` que sert
  l'API Pixel Office. La recalibration reste une décision manuelle.
- **Paper trading (TOP10) retiré le 2026-08-22** — jobs daemon, route API et
  section du digest hebdo supprimés. `paper_mvp.py` reste dans le repo : sa
  fonction `_fetch_quote` est réutilisée par le script de prix live des
  positions patrimoine (`/root/agents/alphabrief/scripts/positions_dashboard.py`).
  Ses fonctions de rebalance (`run_weekly_rebalance`, `run_daily_nav`) ne sont
  plus appelées par personne — ne pas les relancer sans en reparler à Max.
- **`alerts` et `portfolio_holdings` n'existent pas**, et ne sont pas recréées
  dans le schéma local. Le frontend interroge pourtant `alerts` à 5 endroits.
  La fonctionnalité d'alertes n'a jamais tourné. On ne recrée pas une table
  pour faire taire du code mort : la surface se tranche au lot 4.
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
