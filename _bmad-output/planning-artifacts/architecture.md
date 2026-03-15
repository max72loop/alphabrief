---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments: [prd.md]
workflowType: 'architecture'
project_name: 'Mytrader Generator'
user_name: 'Max'
date: '2026-01-24'
status: 'complete'
completedAt: '2026-01-24'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
29 FRs couvrant 6 domaines de capacité. Le coeur est le scoring algorithmique (score potentiel, confiance, importance) avec une page détaillée modulable comme différenciateur UI principal.

**Non-Functional Requirements:**
- Performance : scoring < 5s, pages < 2s, batch parallèle
- Intégration : résilience yfinance (retry x3, mode dégradé)
- Maintenabilité : backend découplé, stockage migrable, extensible auth

**Scale & Complexity:**
- Primary domain: web full-stack (Flask + JS vanilla)
- Complexity level: low-medium
- Estimated architectural components: 8-10 (routes, templates, static, models, providers, scoring, storage, utils)

### Technical Constraints & Dependencies

- Backend Python existant réutilisé tel quel (providers, scoring, features, watchlist)
- Dépendance externe unique : yfinance (Yahoo Finance API non-officielle)
- Stockage JSON local (pas de base de données au MVP)
- JavaScript vanilla + SortableJS pour le drag & drop
- Pas de SEO, pas de temps réel, pas d'auth au MVP

### Cross-Cutting Concerns Identified

- Gestion d'erreurs réseau (retry, fallback, messages utilisateur)
- Normalisation tickers internationaux (30+ formats de bourses)
- Persistance préférences UI (disposition des sections par ticker)
- Abstraction stockage (JSON → DB future migration)
- Architecture extensible (ajout auth sans refonte)

## Starter Template Evaluation

### Primary Technology Domain

Web full-stack Python (Flask + Jinja2 + JS vanilla), basé sur l'analyse des exigences projet.

### Starter Options Considered

| Option | Description | Retenue |
|--------|-------------|:---:|
| Flask minimal (app.py unique) | Un seul fichier | Non — pas extensible |
| Flask + Blueprints + Application Factory | Structure modulaire | **Oui** |
| Flask Mega-Tutorial structure | Structure éducative complète | Non — trop pour MVP |
| Cookiecutter Flask | Template générique complet | Non — trop opinionated |

### Selected Starter: Flask Application Factory + Blueprints

**Rationale :**
- Blueprints organisent les routes par domaine (watchlist, portfolio, scoring, detail)
- Application Factory facilite testing et configuration multi-environnements
- Structure légère pour MVP solo, scalable pour multi-utilisateurs

**Project Structure:**

```
mytrader/
├── app/
│   ├── __init__.py              # Application factory (create_app)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── watchlist.py         # Blueprint watchlist
│   │   ├── portfolio.py         # Blueprint portefeuille
│   │   ├── scoring.py           # Blueprint scoring
│   │   └── detail.py            # Blueprint page détaillée
│   ├── templates/
│   │   ├── base.html            # Layout héritable
│   │   ├── watchlist.html
│   │   ├── portfolio.html
│   │   ├── detail.html
│   │   └── components/          # Fragments réutilisables
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── img/
│   └── storage/
│       ├── __init__.py
│       └── json_store.py        # Abstraction stockage JSON
├── scoring/                     # Backend existant (réutilisé)
│   ├── potential.py
│   ├── importance.py
│   └── confidence.py
├── providers/                   # Backend existant (réutilisé)
│   ├── price_identity.py
│   └── fundamentals_yf.py
├── features/                    # Backend existant (réutilisé)
│   ├── momentum.py
│   └── technicals.py
├── utils/                       # Backend existant (réutilisé)
│   └── ticker_utils.py
├── data/                        # Stockage JSON persistant
│   ├── watchlist.json
│   ├── portfolio.json
│   ├── scores_history.json
│   └── ui_preferences.json
├── config.py                    # Configuration Flask
├── run.py                       # Point d'entrée
└── requirements.txt
```

**Architectural Decisions Provided:**

- Language & Runtime: Python 3.10+, Flask 3.x
- Styling: CSS custom (thème sombre migré depuis Streamlit)
- Build Tooling: Pas de bundler JS — fichiers statiques servis directement
- Testing: pytest (post-MVP)
- Code Organization: Blueprints par domaine fonctionnel
- Development Experience: Flask debug mode, hot reload intégré

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Stockage JSON multi-fichiers (un par concept)
- Routes Flask servent les pages directement (pas d'API REST séparée)
- SortableJS pour le drag & drop avec persistance AJAX

**Important Decisions (Shape Architecture):**
- Pattern gestion d'erreurs uniforme (flash messages)
- Historique scores dans un fichier unique
- Préférences UI sauvegardées par ticker

**Deferred Decisions (Post-MVP):**
- Authentification (middleware @login_required)
- Validation données (pydantic)
- CI/CD pipeline
- Base de données (migration JSON → SQLite/PostgreSQL)

### Data Architecture

- Stockage : fichiers JSON dans /data/
- Un fichier par concept : watchlist, portfolio, scores_history, ui_preferences
- Historique : entrées {ticker, score, confidence, date} dans scores_history.json
- Validation : dicts Python simples (pas de pydantic au MVP)
- Abstraction : json_store.py encapsule lecture/écriture (migrable vers DB)

### Authentication & Security

- Pas d'auth au MVP (usage local mono-utilisateur)
- Point d'insertion prévu : decorator @login_required sur Blueprints
- Pas de données sensibles exposées

### API & Communication Patterns

- Pas d'API REST séparée — routes Flask servent les pages HTML
- Scoring déclenché par POST avec redirect
- Sauvegarde préférences UI via AJAX (fetch POST)
- Gestion erreurs : flash messages Flask

### Frontend Architecture

- MPA classique — pas de state management JS
- SortableJS pour drag & drop sections (page détaillée)
- CSS custom unique (style.css, thème sombre)
- Pas de bundler, fichiers statiques servis par Flask

### Infrastructure & Deployment

- flask run en local (port 5000, debug mode)
- config.py pour la configuration
- Pas de CI/CD au MVP
- Logging via Flask logger standard

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python (Backend) :**
- Fichiers : snake_case → `watchlist.py`, `json_store.py`
- Fonctions : snake_case → `get_watchlist()`, `compute_score()`
- Classes : PascalCase → `JsonStore`
- Variables : snake_case → `score_history`, `ticker_data`
- Constants : UPPER_SNAKE → `MAX_RETRIES = 3`

**JSON (Données) :**
- Clés : snake_case → `{"ticker": "AAPL", "score_potential": 78, "created_at": "2026-01-24T10:30:00"}`

**HTML/Jinja2 (Templates) :**
- Fichiers : snake_case → `watchlist.html`, `base.html`
- IDs CSS/JS : kebab-case → `id="score-container"`
- Classes CSS : kebab-case → `class="card-detail"`
- Blocs Jinja : snake_case → `{% block page_content %}`

**JavaScript :**
- Fonctions : camelCase → `saveLayout()`, `handleDrop()`
- Variables : camelCase → `currentTicker`, `scoreData`
- Fichiers : kebab-case → `drag-drop.js`, `scoring.js`

**Routes Flask :**
- URLs : kebab-case → `/watchlist`, `/portfolio`, `/detail/<ticker>`
- Fonctions de vue : snake_case → `def show_detail(ticker):`

### Structure Patterns

**Blueprint pattern :**
```python
from flask import Blueprint, render_template, redirect, url_for, flash, request

bp = Blueprint('watchlist', __name__, url_prefix='/watchlist')

@bp.route('/')
def index():
    ...

@bp.route('/add', methods=['POST'])
def add():
    ...
```

**Template pattern :**
- `base.html` : layout principal (nav, head, footer)
- Pages : héritent via `{% extends "base.html" %}`
- Composants : inclus via `{% include "components/score_badge.html" %}`

### Format Patterns

**Données JSON stockées :**
```json
// watchlist.json
{"tickers": ["AAPL", "MC.PA", "9961.HK"]}

// portfolio.json
{"holdings": [{"ticker": "AAPL", "added_at": "2026-01-24"}]}

// scores_history.json
{"entries": [{"ticker": "AAPL", "score": 78, "confidence": 85, "date": "2026-01-24T10:30:00"}]}

// ui_preferences.json
{"layouts": {"AAPL": ["score", "fundamentals", "technicals", "identity"]}}
```

**Dates :** ISO 8601 partout → `"2026-01-24T10:30:00"`

### Process Patterns

**Gestion d'erreurs :**
```python
try:
    result = provider_function(ticker)
except Exception as e:
    flash(f"Erreur pour {ticker}: {str(e)}", "error")
    return redirect(url_for('watchlist.index'))
```

**Retry yfinance :**
```python
for attempt in range(MAX_RETRIES):
    try:
        data = yf.Ticker(ticker).info
        break
    except Exception:
        if attempt == MAX_RETRIES - 1:
            return None
```

**Flash messages :**
- Succès : `flash("message", "success")`
- Erreur : `flash("message", "error")`
- Info : `flash("message", "info")`

### Enforcement Guidelines

**Tous les agents AI DOIVENT :**
- Utiliser snake_case pour Python, camelCase pour JS, kebab-case pour CSS/URLs
- Stocker les dates en ISO 8601
- Utiliser flash messages pour la communication utilisateur
- Encapsuler les appels yfinance dans try/except avec retry
- Passer par json_store.py pour toute lecture/écriture de données
- Hériter de base.html pour tout template de page

## Project Structure & Boundaries

### Complete Project Directory Structure

```
mytrader/
├── app/
│   ├── __init__.py                    # Application factory (create_app)
│   ├── routes/
│   │   ├── __init__.py                # Enregistrement des blueprints
│   │   ├── watchlist.py               # FR1-4 : CRUD watchlist
│   │   ├── portfolio.py               # FR5-8 : CRUD portefeuille + transfert
│   │   ├── scoring.py                 # FR9-13 : Scoring unitaire + batch
│   │   └── detail.py                  # FR17-24 : Page détaillée modulable
│   ├── templates/
│   │   ├── base.html                  # Layout principal (nav, flash, footer)
│   │   ├── watchlist.html             # Liste watchlist + formulaire ajout
│   │   ├── portfolio.html             # Liste portefeuille + scores
│   │   ├── detail.html                # Page détaillée modulable
│   │   ├── history.html               # FR15-16 : Historique scores
│   │   └── components/
│   │       ├── score_badge.html       # Badge score coloré
│   │       ├── ticker_row.html        # Ligne ticker dans les listes
│   │       ├── section_score.html     # Module score (drag & drop)
│   │       ├── section_fundamentals.html
│   │       ├── section_technicals.html
│   │       └── section_identity.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css             # Thème sombre, layout, composants
│   │   ├── js/
│   │   │   ├── drag-drop.js          # SortableJS init + save layout AJAX
│   │   │   └── scoring.js            # Feedback UI pendant le scoring
│   │   └── img/
│   └── storage/
│       ├── __init__.py
│       └── json_store.py             # Abstraction R/W JSON (migrable DB)
├── scoring/                           # Backend existant (réutilisé tel quel)
│   ├── __init__.py
│   ├── potential.py                   # FR11 : Score 0-100
│   ├── importance.py                  # FR13 : Classement métriques
│   └── confidence.py                  # FR12 : Score confiance
├── providers/                         # Backend existant (réutilisé tel quel)
│   ├── __init__.py
│   ├── price_identity.py             # FR25 : Prix + identité
│   └── fundamentals_yf.py            # FR26 : Fondamentaux
├── features/                          # Backend existant (réutilisé tel quel)
│   ├── __init__.py
│   ├── momentum.py                    # FR27 : Momentum 12m
│   └── technicals.py                  # FR27 : RSI, SMA 50/200
├── utils/                             # Backend existant (réutilisé tel quel)
│   ├── __init__.py
│   └── ticker_utils.py               # FR29 : Normalisation tickers
├── data/                              # Stockage JSON persistant
│   ├── watchlist.json
│   ├── portfolio.json
│   ├── scores_history.json            # FR14 : Historique scores
│   └── ui_preferences.json            # FR23 : Layouts sauvegardés
├── config.py                          # Configuration Flask (DEBUG, paths)
├── run.py                             # Point d'entrée : python run.py
├── requirements.txt                   # Flask, yfinance, pandas, numpy
└── .gitignore
```

### Architectural Boundaries

**Route Boundaries (Blueprints) :**

| Blueprint | URL Prefix | Responsabilité |
|-----------|-----------|----------------|
| watchlist | `/watchlist` | FR1-4 : Gestion watchlist |
| portfolio | `/portfolio` | FR5-8 : Gestion portefeuille |
| scoring | `/scoring` | FR9-13 : Déclenchement scoring |
| detail | `/detail` | FR17-24 : Page entreprise |

**Data Boundaries :**
- Routes → appellent `json_store.py` pour lire/écrire les données
- Routes → appellent `scoring/` et `providers/` pour le scoring
- `json_store.py` est le seul point d'accès aux fichiers JSON
- Le backend existant ne connaît pas Flask (pas de dépendance inverse)

**Frontend Boundaries :**
- Jinja2 gère le rendu HTML côté serveur
- JavaScript ne gère que le drag & drop et la sauvegarde AJAX du layout
- Pas de communication JS → backend sauf pour `/detail/save-layout` (POST AJAX)

### Requirements to Structure Mapping

| FR | Fichier principal | Fichiers liés |
|----|-------------------|---------------|
| FR1-4 | routes/watchlist.py | templates/watchlist.html, storage/json_store.py |
| FR5-8 | routes/portfolio.py | templates/portfolio.html, storage/json_store.py |
| FR9-10 | routes/scoring.py | scoring/*, providers/*, features/* |
| FR11-13 | scoring/*.py | providers/*, features/* |
| FR14-16 | routes/scoring.py | templates/history.html, storage/json_store.py |
| FR17-24 | routes/detail.py | templates/detail.html, static/js/drag-drop.js |
| FR25-29 | providers/*.py, features/*.py, utils/*.py | (backend existant) |

### Data Flow

```
User Action (navigateur)
    ↓
Flask Route (blueprint)
    ├→ json_store.py (lecture données)
    ├→ providers/*.py (fetch yfinance)
    ├→ features/*.py (calcul indicateurs)
    ├→ scoring/*.py (calcul scores)
    ├→ json_store.py (écriture résultats)
    ↓
Jinja2 Template (rendu HTML)
    ↓
Navigateur (affichage)
    ↓ (drag & drop uniquement)
AJAX POST → /detail/save-layout → json_store.py
```

### External Integrations

- **Yahoo Finance (yfinance)** : Seule intégration externe
  - Point d'entrée : `providers/price_identity.py` et `providers/fundamentals_yf.py`
  - Retry x3 avec fallback gracieux
  - Données non-cachées (scoring à la demande)

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
Toutes les décisions technologiques sont mutuellement compatibles. Flask 3.x + Jinja2 + Blueprints forment un stack cohérent. Le backend existant (providers, scoring, features) reste indépendant de Flask sans dépendance inverse.

**Pattern Consistency:**
Les conventions de nommage sont non-ambiguës (snake_case Python, camelCase JS, kebab-case CSS/URLs). Les patterns Blueprint, template inheritance et flash messages sont uniformes.

**Structure Alignment:**
La structure de répertoires reflète exactement les Blueprints et le mapping FR. Les boundaries data (json_store.py unique point d'accès) sont respectées dans toute l'architecture.

### Requirements Coverage ✅

**Functional Requirements:** 29/29 FRs couverts architecturalement.
**Non-Functional Requirements:** Performance, intégration et maintenabilité adressés par les patterns documentés.

### Implementation Readiness ✅

**Decision Completeness:** Toutes les décisions critiques documentées avec versions.
**Structure Completeness:** Arbre projet complet avec annotations FR.
**Pattern Completeness:** Exemples de code pour chaque pattern critique.

### Gap Analysis

**Critical Gaps:** Aucun
**Important Gaps:** ThreadPoolExecutor pour batch scoring à détailler lors de l'implémentation.
**Deferred by Design:** Tests, CI/CD, pydantic, authentification.

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**✅ Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**✅ Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**✅ Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High

**Key Strengths:**
- Backend existant réutilisé sans modification
- Abstraction stockage préparant la migration future
- Structure modulaire extensible (auth, multi-users)
- Patterns concrets avec exemples de code

**Areas for Future Enhancement:**
- Ajout authentification (Phase 2)
- Migration stockage JSON → base de données
- CI/CD pipeline
- Validation données avec pydantic

### Implementation Handoff

**AI Agent Guidelines:**
- Suivre toutes les décisions architecturales exactement comme documentées
- Utiliser les patterns d'implémentation de manière cohérente
- Respecter la structure projet et les boundaries
- Consulter ce document pour toute question architecturale

**First Implementation Priority:**
Initialisation du projet Flask : `create_app` factory, blueprints vides, `base.html`, `run.py`, `requirements.txt`

## Architecture Completion Summary

### Workflow Completion

**Architecture Decision Workflow:** COMPLETED ✅
**Total Steps Completed:** 8
**Date Completed:** 2026-01-24
**Document Location:** _bmad-output/planning-artifacts/architecture.md

### Final Architecture Deliverables

- 15+ décisions architecturales documentées avec versions
- 6 catégories de patterns d'implémentation définis
- 8-10 composants architecturaux spécifiés
- 29/29 exigences fonctionnelles couvertes

### Development Sequence

1. Initialiser le projet Flask (create_app, blueprints, base.html, run.py)
2. Configurer l'environnement (config.py, requirements.txt, .gitignore)
3. Implémenter json_store.py (abstraction stockage)
4. Intégrer le backend existant (scoring/, providers/, features/, utils/)
5. Construire les features par Blueprint en suivant les patterns établis

---

**Architecture Status:** READY FOR IMPLEMENTATION ✅

