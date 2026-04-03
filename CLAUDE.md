# AlphaBrief

Screener quantitatif d'actions. Score chaque ticker de 0 à 100 via fondamentaux, techniques et momentum. Freemium : 5 tickers/jour gratuits, illimité en premium.

## Stack

- **Backend** : Python scheduler sur Hetzner VPS (95.217.239.25), géré par PM2
- **Base** : Supabase (auth, storage, tables de scores)
- **Frontend** : Next.js déployé sur maxloop.ovh
- **Data** : API FMP (Financial Modeling Prep) — ne plus utiliser Yahoo Finance
- **Paiements** : Lemon Squeezy (intégration prévue)

## Architecture

```
Python scheduler (cron PM2)
    → fetch FMP API
    → calcul scores (fondamentaux, techniques, momentum)
    → upsert Supabase
Next.js frontend (maxloop.ovh)
    → lecture Supabase
    → affichage scores, UI dark Hyperliquid-style
```

## Commandes courantes

- `pm2 status` : vérifier les process actifs
- `pm2 logs alphabrief` : logs du scheduler
- `pm2 restart alphabrief` : redémarrer le scheduler
- `supabase db reset` : reset local (jamais en prod)

## Règles critiques

- TOUJOURS utiliser le heredoc Python (`python3 << 'PYEOF'`) pour écrire des fichiers sur le VPS — les bash heredocs corrompent les caractères
- Ne JAMAIS mentionner "conseil en investissement" — AlphaBrief est un outil d'aide à la décision, pas du conseil financier
- Préférer `--break-system-packages` avec pip sur le VPS (Ubuntu 24.04, pas de venv)
- Les variables d'environnement sensibles (clés FMP, Supabase, Lemon Squeezy) sont dans `.env` — ne jamais les commiter

## Scoring

Le score 0-100 combine trois piliers :
- Fondamentaux (inspiré Brian Feroldi, Quality of Earnings)
- Techniques (RSI, moyennes mobiles)
- Momentum (performance relative)

Chaque pilier a un poids configurable. Le scoring inclut une classification adaptative par type d'action (growth, value, dividend, etc.).

## Gotchas

- Le VPS tourne sur Ubuntu 24.04 sans venv — toujours `pip install X --break-system-packages`
- Le frontend Next.js et le scheduler Python sont deux codebases séparées, pas un monorepo
- Les données FMP ont des rate limits — implémenter du caching/throttling
- L'ancien nom du projet est "MyTrader" — certains fichiers ou refs peuvent encore utiliser ce nom
