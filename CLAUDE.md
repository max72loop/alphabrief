# AlphaBrief

Screener quantitatif d'actions. Score chaque ticker de 0 à 100 via fondamentaux, techniques et momentum. Freemium : 5 analyses/jour gratuites, illimité en premium.

## Stack

- **Backend** : Python (Flask + APScheduler), scheduler toutes les 4h
- **Base** : Supabase (auth, tables de scores, watchlists, profiles)
- **Frontend** : Next.js (React 19, Tailwind v4, Supabase SSR)
- **Data** : yfinance (actuel) — migration vers FMP (Financial Modeling Prep) prévue
- **Paiements** : Lemon Squeezy — webhook implémenté, checkout URL à configurer
- **LLM** : DeepSeek — enrichissement business snapshot (one_liner, moat_tags, catalysts)

## Architecture

```
Python scheduler (APScheduler)
    → fetch yfinance / FMP
    → calcul scores (fondamentaux, techniques, momentum)
    → upsert Supabase (ticker_scores + champs enrichis)

Next.js frontend
    → auth Supabase SSR
    → lecture ticker_scores
    → /dashboard  : screener filtrable (secteur, score min, watchlist)
    → /ticker/[symbol] : page detail (scores, facteurs, métriques)
    → /pricing    : Free vs Premium, CTA Lemon Squeezy
```

## Schéma Supabase

### ticker_scores
Colonnes principales : `ticker`, `company_name`, `sector`, `exchange`, `currency`, `market_cap`, `one_liner`, `moat_tags`, `score_total`, `score_fundamentals`, `score_technicals`, `score_momentum`, `score_label`, `importance_items` (jsonb), `financials` (jsonb), `market_data` (jsonb), `score_date`, `computed_at`

### profiles
`id` (FK auth.users), `is_premium`, `lemon_order_id`, `analyses_today`, `last_analysis_date`, `updated_at`

### watchlists / watchlist_tickers
`watchlists` : `id`, `user_id` (FK auth.users)
`watchlist_tickers` : `watchlist_id`, `ticker`

## Variables d'environnement

### Backend (`alphabrief/.env`)
```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
DEEPSEEK_API_KEY=
FMP_API_KEY=
```

### Frontend (`alphabrief-frontend/.env.local`)
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
LEMON_WEBHOOK_SECRET=
NEXT_PUBLIC_LEMON_CHECKOUT_URL=
```

## Scoring

Le score 0–100 combine trois piliers :
- **Fondamentaux** (50%) : inspiré Brian Feroldi / Quality of Earnings — croissance, marges, ROIC, dette, dilution
- **Techniques** (25%) : RSI 14, SMA 50/200, MACD, drawdown, volatilité
- **Momentum** (25%) : performance 1/3/6/12 mois relative au marché et au secteur

Chaque pilier a un poids configurable dans `config.py`. Classification adaptative par type d'action (growth, value, dividend...).

## Déploiement VPS (95.217.239.25)

### Premier déploiement
```bash
ssh root@95.217.239.25
cd /root/alphabrief
git pull
cp .env.example .env   # puis remplir les vraies valeurs
mkdir -p logs
npm install -g pm2
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup             # coller la commande affichée
```

### Mise à jour du code
```bash
ssh root@95.217.239.25
cd /root/alphabrief && git pull
pm2 restart alphabrief
```

### Commandes PM2 utiles
```bash
pm2 logs alphabrief          # logs en temps réel
pm2 status                   # état du process
pm2 restart alphabrief       # forcer un run immédiat
```

## CLI local

```bash
python -m core.cli analyze AAPL MSFT NVDA   # scorer des tickers précis
python -m core.cli run-all                   # tout scorer (comme le VPS)
python -m core.cli status                    # voir fraîcheur des données en base
```

## Règles critiques

- Ne JAMAIS mentionner "conseil en investissement" — AlphaBrief est un outil d'aide à la décision, pas du conseil financier
- Ne jamais commiter les fichiers `.env` / `.env.local`
- Les deux codebases (`alphabrief/` et `alphabrief-frontend/`) sont séparées, pas un monorepo
- Préférer FMP à yfinance pour les nouvelles features data (yfinance est non-officiel et peut casser)

## Gotchas

- Le cache des cartes est dans `data/cache/*.json` (TTL 2h) et SQLite (`data/mytrader.db`) — certains fichiers référencent encore l'ancien nom "MyTrader"
- Les données FMP ont des rate limits — toujours cacher avant d'appeler l'API
- Le middleware Next.js protège `/dashboard` et `/ticker/*` — redirige vers `/login` si non authentifié
- La limite freemium (5/jour) est à implémenter côté API route `/api/analyze` — le middleware actuel gère uniquement l'auth
