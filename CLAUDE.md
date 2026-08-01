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
- **Data** : FMP pour les fondamentaux US, yfinance en repli — voir « Gotchas »
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
    APScheduler : scoring 7h · health /30min · cache cleanup 3h
                  paper_mvp weekly lundi 14h UTC · nav daily 22h UTC
    Importe core.generator, core.storage.writer, core.providers.events_yf
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

- **FMP est en 429 permanent** sur le plan actuel. `fundamentals_yf` court-circuite
  FMP pour les tickers internationaux (suffixes Yahoo explicites, pour ne pas
  exclure BRK.B) et bascule sur yfinance. `paper_mvp.py` est entièrement sur
  yfinance pour la même raison.
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
- Le cache des cartes est dans `data/cache/*.json` (TTL 2h) et SQLite
  (`data/mytrader.db`) — certains fichiers portent encore l'ancien nom « MyTrader ».
- L'app Flask v1 est archivée : tag `archive/flask-v1`, branche `archive/flask`.
  Restauration : `git checkout archive/flask-v1 -- app/`.
- `core/paper_portfolio/` est gelé (36 `NotImplementedError`). Ses 154 tests
  échouent par construction — c'est la baseline, pas une régression.
- `core/bitcoin/` est conservé en lecture seule comme source de données
  optionnelle sur BTC, hors du chemin critique.
