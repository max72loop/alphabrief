# AlphaBrief

Suivi de patrimoine personnel, mono-utilisateur, sans intention commerciale.
Voir ses investissements répartis sur plusieurs supports au même endroit,
garder des notes éditables sur les sociétés suivies, et se faire relancer
chaque semaine pour saisir les nouveaux chiffres.

Ce n'est plus un screener vendu en SaaS. Toute la logique de facturation a été
retirée au lot 1 (2026-07-31).

## Stack

- **Backend** : Python (lib de scoring importée par le daemon — voir « Runtime »)
- **Base** : Supabase (auth + Postgres)
- **Frontend** : Next.js 16 (React 19, Tailwind v4, Supabase SSR), déployé sur Vercel
- **Data** : FMP pour les fondamentaux US, yfinance en repli — voir « Gotchas »
- **LLM** : DeepSeek — enrichissement business snapshot

## Runtime

Ce repo est une **librairie** (`core/`, `utils/`) consommée par deux runtimes :

```
/root/agents/alphabrief/main.py   ← daemon de prod (PM2 "alphabrief")
    APScheduler : scoring 7h · health /30min · cache cleanup 3h
                  paper_mvp weekly lundi 14h UTC · nav daily 22h UTC
    Importe core.generator, core.storage.supabase_writer, core.providers.events_yf
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

**Totale sur la base miroir. Nulle sur Supabase.**

Commits en local : libres. Sur la miroir : appliquer, casser, recréer, rejouer
depuis zéro autant de fois que nécessaire, sans rien demander.

Demandent un feu vert explicite de Max :

- **push sur la branche déployée** — Vercel déploie depuis `main` du frontend,
  donc un push est une mise en production, pas un geste de versioning
- **application d'une migration** sur Supabase
- **modification de variables d'environnement**
- **suppression de table**

### Base miroir — `make db-reset`

Postgres 16 local sur le VPS, base `alphabrief_mirror`, **jetable, sans aucune
donnée réelle, jamais**. `db/mirror/` contient l'amorçage (rôles `anon` /
`authenticated` / `service_role` et schéma `auth`, que Supabase fournit d'office
et qu'un Postgres nu n'a pas), la reconstitution de l'état initial, et les
assertions.

```
make db-reset      # base vide -> état cible, en une commande. Échoue au premier problème.
make db-check      # rejoue les assertions seules
make db-policies   # pg_policies, même requête qu'en prod
```

`db-reset` enchaîne : base jetable → bootstrap → état initial → migrations →
assertions → **rejeu des migrations + assertions** (l'idempotence est vérifiée
mécaniquement, pas par relecture).

**Une migration ne part en prod qu'après être passée au vert sur la miroir, avec
la sortie collée dans la livraison.** Le parseur `pglast` passe au second rang :
il valide la syntaxe, pas la sémantique.

Ce que la miroir a déjà attrapé et que `pglast` ne voyait pas : le bloc `paper_*`
de la migration RLS créait ses policies sans `DROP` préalable — correct en
syntaxe, `ERROR: policy already exists` au second passage.

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
- **`alerts` et `portfolio_holdings` n'existent pas** dans le projet Supabase
  (PGRST205), alors que le repo contient leur DDL et que le frontend les
  interroge. Les appels échouent en silence. À trancher : créer, ou retirer
  la surface.
- Le cache des cartes est dans `data/cache/*.json` (TTL 2h) et SQLite
  (`data/mytrader.db`) — certains fichiers portent encore l'ancien nom « MyTrader ».
- L'app Flask v1 est archivée : tag `archive/flask-v1`, branche `archive/flask`.
  Restauration : `git checkout archive/flask-v1 -- app/`.
- `core/paper_portfolio/` est gelé (36 `NotImplementedError`). Ses 154 tests
  échouent par construction — c'est la baseline, pas une régression.
- `core/bitcoin/` est conservé en lecture seule comme source de données
  optionnelle sur BTC, hors du chemin critique.
