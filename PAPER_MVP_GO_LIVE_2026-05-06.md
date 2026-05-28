# Paper Trading MVP — GO LIVE 2026-05-06

**Branche stratégie** : MVP simple (shortcut Phase 3B), 244 lignes Python, 1 smoke test
**Portfolio Supabase** : `TOP10` (id=2), $100,000 initial, started_at 2026-05-06
**Câblage PM2** : `alphabrief` reloaded, jobs `paper_mvp_weekly` + `paper_mvp_nav_daily` actifs

---

## État avant / après

| Item | Avant | Après |
|---|---|---|
| `core/paper_portfolio/` | 154 tests, 113 fail, 0 trade jamais | **frozen** (README explicite) |
| `paper_mvp.py` | n'existait pas | **244 lignes**, smoke test pass |
| `test_paper_mvp_smoke.py` | n'existait pas | **1 test PASS** (0.20s) |
| `paper_portfolios` (Supabase) | 0 lignes | 1 ligne `TOP10` id=2 |
| `paper_positions` | 0 lignes | **6 LONG positions** (TSM, KO, MSFT, UBER, NFLX, COST) |
| `paper_rebalances` | 0 lignes | **6 BUY rows** (run live aujourd'hui) |
| `paper_nav_history` | 0 lignes | **1 row** ⚠ inflée (cf. bug ci-dessous) |
| PM2 alphabrief autorestart | True | True |
| PM2 alphabrief max_memory | 200 MB (saturé à 199.8) | **300 MB** (RSS post-restart 117 MB) |
| Scheduler jobs | scoring + report + health + cleanup | + **paper_mvp_weekly** + **paper_mvp_nav_daily** |

---

## Calendrier des prochains runs

| Job | Cron (UTC) | Prochaine occurrence |
|---|---|---|
| `paper_mvp_weekly` | `mon 14:00 UTC` | **2026-05-11 14:00 UTC** (lundi) |
| `paper_mvp_nav_daily` | `mon-fri 22:00 UTC` | **2026-05-07 22:00 UTC** (jeudi soir) ⚠ |

⚠ Le NAV daily de **ce soir 22:00 UTC** ne tournera pas — le cron est `mon-fri` et aujourd'hui (mercredi 2026-05-06 16:38 UTC) il est passé. **Premier NAV automatique** = jeudi 2026-05-07 22:00 UTC.

---

## ⚠ État pollué à nettoyer manuellement (avant lundi recommandé)

Le run live d'aujourd'hui a été exécuté avec une version du code qui ne persistait pas le cash post-rebalance. Résultat : `paper_nav_history` contient une ligne avec `nav=$159,975` au lieu de `$100,000` (double comptabilité long + cash).

**Le bug est fixé** dans le code actuel (le rebalance écrit désormais sa propre ligne NAV au close), mais les triggers `forbid_mutation()` empêchent supabase-py de DELETE les lignes append-only existantes.

### SQL de nettoyage à exécuter dans Supabase SQL Editor

```sql
-- 1. Désactiver les triggers append-only le temps du cleanup
ALTER TABLE paper_rebalances     DISABLE TRIGGER tr_paper_rebalances_append_only;
ALTER TABLE paper_nav_history    DISABLE TRIGGER tr_paper_nav_history_append_only;

-- 2. Effacer les données polluées du portfolio TOP10 (id=2)
DELETE FROM paper_positions      WHERE portfolio_id = 2;
DELETE FROM paper_rebalances     WHERE portfolio_id = 2;
DELETE FROM paper_nav_history    WHERE portfolio_id = 2;

-- 3. Réactiver les triggers
ALTER TABLE paper_rebalances     ENABLE TRIGGER tr_paper_rebalances_append_only;
ALTER TABLE paper_nav_history    ENABLE TRIGGER tr_paper_nav_history_append_only;

-- 4. (Optionnel) Reset paper_portfolios.started_at pour repartir lundi 2026-05-11
UPDATE paper_portfolios SET started_at = NULL WHERE id = 2;
```

Après nettoyage, le scheduler PM2 prendra naturellement le relais lundi 2026-05-11 14:00 UTC (premier rebalance propre, qui appellera `bootstrap_portfolio()` et restampera `started_at` à cette date).

**Si tu choisis de NE PAS nettoyer** : le rebalance de lundi lira `last_nav=$159,975` et calculera `per_position=$15,997`. Il sur-allouera les 6-7 premiers buy puis logguera "no cash left" pour le reste. Pas catastrophique mais sizing faux pour 1 semaine, et la NAV continuera d'être inflée jusqu'à un rebalance qui clôture toutes les positions (ne se produira pas si le top 10 est stable).

---

## Découverte : couverture FMP partielle

Sur les 10 tickers du top scoring actuel, **4 retournent HTTP 402 Payment Required sur FMP** (`/quote`) :

| Ticker | Type | Notes |
|---|---|---|
| `RDDT` | US (Reddit) | IPO récent, pas dans Starter tier |
| `MC.PA` | non-US (Paris) | requires international plan |
| `RPI.L` | non-US (London) | requires international plan |
| `VLO` | US (Valero) | bloqué malgré US — à investiguer |

Le bot a correctement skippé ces 4 tickers (conforme à la spec) et acheté les 6 disponibles équipondéré. **À considérer** : filtrer en amont `ticker_scores` aux tickers FMP-supportés, ou upgrader le plan FMP. Pour l'instant, accepter le 60-80% fill rate.

---

## Commandes de monitoring

### Supabase (à coller dans le SQL Editor)

```sql
-- 7 derniers jours de NAV
SELECT * FROM paper_nav_history
ORDER BY date DESC LIMIT 7;

-- 20 derniers trades
SELECT * FROM paper_rebalances
ORDER BY rebalance_date DESC, id DESC LIMIT 20;

-- Positions actuelles + valorisation théorique (si la table a les bons indexs)
SELECT p.ticker, p.shares, p.entry_price,
       p.shares * p.entry_price AS notional_at_entry
FROM paper_positions p
WHERE p.portfolio_id = (SELECT id FROM paper_portfolios WHERE name = 'TOP10')
ORDER BY notional_at_entry DESC;
```

### PM2 / VPS

```bash
# Logs spécifiques au paper MVP
pm2 logs alphabrief | grep -i paper_mvp

# Si rien ne s'écrit dans paper_nav_history avant la fin de la semaine,
# vérifier les logs PM2 du process alphabrief :
pm2 logs alphabrief | grep paper_mvp
# Et la santé du process :
pm2 describe alphabrief
```

---

## Run manuels (si besoin de re-tester ou rattraper)

```bash
cd /root/agents/alphabrief
python3 paper_mvp.py --bootstrap   # idempotent, crée TOP10 si absent
python3 paper_mvp.py --rebalance   # forçage manuel d'un rebalance
python3 paper_mvp.py --nav         # forçage manuel d'une NAV row du jour
```

---

## TODOs restants (par ordre)

| # | Action | Effort | Quand |
|---|---|---|---|
| 1 | **Cleanup SQL Supabase** (cf. section ci-dessus) | S | Avant lundi 2026-05-11 14h UTC, idéalement |
| 2 | **Vérifier jeudi 2026-05-07 ~22h05 UTC** que le premier NAV daily a écrit 1 row | XS | Demain soir |
| 3 | **Vérifier lundi 2026-05-11 ~14h05 UTC** que le rebalance a tourné (post-cleanup → 0 SELL + 10 BUY théoriques, en pratique 6-7 BUY à cause de FMP) | XS | Lundi prochain |
| 4 | (Optionnel) **Test résilience FMP partielle** : ajouter un test "FMP renvoie None pour 1 ticker sur 10, vérifier 9 BUY + 1 skip log" — recommandé après 1-2 semaines de data live | S | Quand stable |
| 5 | (Optionnel) **Vue web minimale** sur Vercel/Next.js : équity curve depuis `paper_nav_history` + table positions ouvertes | S/M | Après 4+ semaines de data |
| 6 | (Optionnel) **Filtrer ticker_scores aux tickers FMP-supportés** ou upgrader plan FMP pour 100% fill rate | S | Si fill rate < 70% gêne |
| 7 | **Renommage `/root/agents/alphabrief/` vs `/root/alphabrief/`** pour lever la confusion | S/M | Quand l'occasion se présente |

---

## Récap commits / fichiers modifiés

`/root/agents/alphabrief/` n'est pas un repo git, donc pas de hash de commit. Fichiers touchés :

| Fichier | Action |
|---|---|
| `/root/agents/alphabrief/paper_mvp.py` | **créé** (244 lignes, fix NAV-write inclus) |
| `/root/agents/alphabrief/test_paper_mvp_smoke.py` | **créé** (127 lignes, 1 test) |
| `/root/agents/alphabrief/main.py` | **modifié** (+wrappers safe + 2 add_job timezone="UTC" + log message) |
| `/root/alphabrief/core/paper_portfolio/README.md` | **créé** (freeze notice Phase 3B) |
| PM2 ecosystem | reload + max_memory_restart 200→300 MB + pm2 save |

**Infrastructure totale post-MVP** :
- 1 portfolio actif Supabase (`TOP10` id=2)
- 6 positions LONG (à corriger après cleanup ou laisser dégrader 1 semaine)
- 2 cron jobs APScheduler timezone UTC
- 0 dépendance ajoutée (FMP client + supabase-py + APScheduler étaient déjà là)
