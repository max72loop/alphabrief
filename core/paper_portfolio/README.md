# Paper Portfolio — FROZEN (Phase 3B skeletons)

**État au 2026-05-06** : ce module est gelé. Toutes les fonctions lèvent `NotImplementedError`. Il représente une Phase 3B ambitieuse (hash-chain SHA256, dollar-neutral L/S, corporate actions, métriques annualisées Sharpe/Sortino/alpha-beta) qui a été **jugée sur-dimensionnée** pour l'objectif initial (valider que la méthodologie de scoring 50/25/25 a du sens en simulé).

## Le MVP vit ailleurs

Le paper trading actif est dans :

```
/root/agents/alphabrief/paper_mvp.py
```

Câblé dans le scheduler PM2 actif `/root/agents/alphabrief/main.py` (jobs `paper_mvp_weekly` lundi 14h UTC + `paper_mvp_nav_daily` lun-ven 22h UTC).

Le MVP réutilise les **mêmes tables Supabase** que ce module (`paper_portfolios`, `paper_positions`, `paper_rebalances`, `paper_nav_history`, `paper_missed_rebalances`) — la migration `migrations/supabase_paper_portfolio_001_init.sql` est partagée.

## Quand dégeler ce module ?

À reprendre uniquement si :
- le MVP a 6+ mois de track record convaincant et qu'on veut publier un audit-bundle public (hash-chain SHA256 → preuve immuable forward-test)
- besoin réel de stratégie long-short dollar-neutral
- besoin réel de gestion fine des corporate actions (splits, dividendes, M&A)
- audit académique formel demandé

Sinon, **laisser dormir**. Les 154 tests TDD existants (`tests/core/paper_portfolio/`) restent une spec utile pour quiconque relance la Phase 3B un jour.
