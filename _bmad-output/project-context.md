---
project_name: 'Mytrader Generator'
user_name: 'Max'
date: '2026-01-24'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'naming', 'data_storage', 'error_handling', 'critical_rules']
existing_patterns_found: 8
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- Python 3.10+
- Flask 3.x (Application Factory + Blueprints)
- Jinja2 (templating, inclus avec Flask)
- JavaScript vanilla (pas de framework)
- SortableJS (drag & drop)
- yfinance (Yahoo Finance, API non-officielle)
- pandas, numpy (calculs financiers)
- Stockage : fichiers JSON locaux (pas de DB au MVP)

## Critical Implementation Rules

### Python / Flask Rules

- TOUJOURS utiliser l'Application Factory pattern (`create_app()` dans `app/__init__.py`)
- TOUJOURS organiser les routes en Blueprints par domaine : watchlist, portfolio, scoring, detail
- JAMAIS importer Flask app directement — utiliser `current_app` si besoin du contexte
- TOUJOURS passer par `storage/json_store.py` pour lire/écrire les fichiers JSON — jamais d'accès fichier direct dans les routes
- TOUJOURS encapsuler les appels yfinance dans try/except avec retry x3
- Retourner `None` si toutes les tentatives échouent (mode dégradé)
- TOUJOURS utiliser `flash()` pour communiquer les erreurs à l'utilisateur (catégories : success, error, info)
- TOUJOURS redirect après un POST (pattern POST-Redirect-GET)

### Naming Conventions

- **Python** : snake_case (fichiers, fonctions, variables), PascalCase (classes), UPPER_SNAKE (constantes)
- **JavaScript** : camelCase (fonctions, variables), kebab-case (fichiers)
- **HTML/CSS** : kebab-case (classes, IDs, fichiers)
- **URLs Flask** : kebab-case (`/watchlist`, `/detail/<ticker>`)
- **JSON keys** : snake_case (`score_potential`, `created_at`)
- **Dates** : ISO 8601 partout (`2026-01-24T10:30:00`)

### Template Rules

- TOUJOURS hériter de `base.html` via `{% extends "base.html" %}`
- Utiliser `{% include "components/xxx.html" %}` pour les fragments réutilisables
- Nommer les blocs Jinja en snake_case : `{% block page_content %}`
- JAMAIS de logique métier dans les templates — uniquement affichage

### JavaScript Rules

- JavaScript ne gère QUE le drag & drop (SortableJS) et la sauvegarde layout AJAX
- Un seul endpoint AJAX : `POST /detail/save-layout`
- Pas de state management JS — c'est du MPA classique
- Pas de bundler — fichiers statiques servis directement par Flask

### Data Storage Rules

- 4 fichiers JSON dans `/data/` : watchlist.json, portfolio.json, scores_history.json, ui_preferences.json
- Formats :
  - watchlist : `{"tickers": ["AAPL", "MC.PA"]}`
  - portfolio : `{"holdings": [{"ticker": "AAPL", "added_at": "2026-01-24"}]}`
  - scores_history : `{"entries": [{"ticker": "AAPL", "score": 78, "confidence": 85, "date": "2026-01-24T10:30:00"}]}`
  - ui_preferences : `{"layouts": {"AAPL": ["score", "fundamentals", "technicals", "identity"]}}`
- json_store.py est le SEUL point d'accès — jamais `open()` + `json.load()` ailleurs

### Backend Existant (NE PAS MODIFIER)

- `scoring/` : potential.py, importance.py, confidence.py — réutiliser tel quel
- `providers/` : price_identity.py, fundamentals_yf.py — réutiliser tel quel
- `features/` : momentum.py, technicals.py — réutiliser tel quel
- `utils/` : ticker_utils.py — réutiliser tel quel
- Ces modules ne connaissent PAS Flask — pas de dépendance inverse

### Error Handling Pattern

```python
MAX_RETRIES = 3

# Retry yfinance
for attempt in range(MAX_RETRIES):
    try:
        data = yf.Ticker(ticker).info
        break
    except Exception:
        if attempt == MAX_RETRIES - 1:
            return None

# Route error handling
try:
    result = provider_function(ticker)
except Exception as e:
    flash(f"Erreur pour {ticker}: {str(e)}", "error")
    return redirect(url_for('watchlist.index'))
```

### Critical Don't-Miss Rules

- JAMAIS d'API REST séparée — les routes Flask servent directement les pages HTML
- JAMAIS de JavaScript sauf pour drag & drop et save layout
- JAMAIS de modification des modules backend existants (scoring/, providers/, features/)
- JAMAIS de `open()` direct sur les fichiers JSON — toujours json_store.py
- JAMAIS de SEO, meta tags ou SSR optimization — usage local uniquement
- JAMAIS d'auth au MVP — mais l'architecture supporte `@login_required` futur
- Les tickers sont internationaux (30+ bourses) — toujours utiliser ticker_utils.py pour normaliser
- ThreadPoolExecutor pour le scoring batch (parallélisme)
