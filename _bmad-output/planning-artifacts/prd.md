---
stepsCompleted: [step-01-init, step-02-discovery, step-03-success, step-04-journeys, step-05-domain, step-06-innovation, step-07-project-type, step-08-scoping, step-09-functional, step-10-nonfunctional, step-11-polish, step-12-complete]
inputDocuments: []
workflowType: 'prd'
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 0
  projectDocs: 0
classification:
  projectType: web_app
  domain: fintech
  complexity: medium
  projectContext: brownfield
---

# Product Requirements Document - Mytrader Generator

**Author:** Max
**Date:** 2026-01-24

## Executive Summary

MyTrader Generator est un outil personnel de surveillance et scoring d'actions/investissements. Actuellement construit en Streamlit, le projet migre vers Flask pour obtenir une liberté totale sur le UI.

**Différenciateur :** Page détaillée par entreprise entièrement modulable (sections réorganisables par drag & drop), combinée à un algorithme de scoring propriétaire multi-critères (fondamentaux + techniques).

**Utilisateur cible :** Investisseur actif (Max) souhaitant évaluer rapidement le potentiel d'une action et suivre l'évolution de ses notations dans le temps.

**Contexte technique :** Migration brownfield — le backend existant (providers yfinance, scoring, watchlist) est déjà découplé du UI Streamlit et sera réutilisé tel quel avec Flask.

## Success Criteria

### User Success
- Consulter watchlist et portefeuille d'un coup d'oeil
- Scorer n'importe quelle action en un clic
- Suivre l'évolution d'un score dans l'historique
- Personnaliser la page détaillée (afficher/masquer/réorganiser les sections)

### Business Success
- Outil fonctionnel en usage personnel quotidien
- Architecture prête pour multi-utilisateurs à terme
- Remplacement complet de la version Streamlit

### Technical Success
- Interface Flask réactive et fluide
- Architecture extensible (multi-utilisateurs, authentification future)
- UI modulable (sections configurables)
- Backend existant réutilisé sans modification

### Measurable Outcomes
- Scoring d'une action < 5 secondes
- Chargement de page < 2 secondes
- Page détaillée affiche : score, fondamentaux, indicateurs techniques, historique

## Product Scope

### MVP (Phase 1)
- Watchlist : ajout, suppression, affichage liste
- Portefeuille : ajout, suppression, affichage avec scores
- Scoring unitaire via bouton (yfinance)
- Scoring batch de la watchlist
- Page détaillée entreprise modulable (drag & drop sections)
- Historique des scores
- Transfert watchlist → portefeuille

### Growth (Phase 2)
- Système d'alertes (RSI, momentum, prix vs SMA, score)
- Export / partage de cartes sociales (SVG)
- Authentification multi-utilisateurs

### Vision (Phase 3)
- Déploiement en ligne (hébergement cloud)
- Comparaison côte-à-côte entre actions
- Tableaux de bord personnalisables

## User Journeys

### Parcours 1 : Découverte et notation d'une action

**Scène d'ouverture :** Max entend parler d'une entreprise intéressante. Il veut rapidement savoir si elle mérite son attention.

**Action montante :** Il ouvre MyTrader, tape le ticker dans la watchlist, clique sur "Scorer". L'algorithme récupère les données financières et génère un score en quelques secondes.

**Climax :** Le score s'affiche — 78/100. Max clique sur la page détaillée : détail du scoring, fondamentaux, indicateurs techniques. Il réorganise les modules pour mettre en avant momentum et valorisation.

**Résolution :** Max ajoute l'action à son portefeuille et suit l'évolution du score au fil des semaines.

### Parcours 2 : Suivi de portefeuille quotidien

**Scène d'ouverture :** Max ouvre l'application le matin pour voir l'état de ses positions.

**Action montante :** Il consulte son portefeuille, voit les scores actuels. Un score a baissé depuis la dernière notation.

**Climax :** Il clique sur l'action, accède à la page détaillée, re-score. Le nouveau score confirme la dégradation des fondamentaux.

**Résolution :** L'historique montre la tendance baissière. Max prend une décision informée.

### Parcours 3 : Gestion de la watchlist

**Scène d'ouverture :** Max fait le ménage dans sa watchlist accumulée.

**Action montante :** Il supprime les actions obsolètes, ajoute de nouvelles découvertes.

**Climax :** Il lance un scoring batch sur toute la watchlist pour une vue d'ensemble à jour.

**Résolution :** Il identifie les meilleures opportunités et les transfère vers son portefeuille.

### Journey Requirements Summary

| Parcours | Capacités requises |
|----------|-------------------|
| Découverte et notation | Ajout watchlist, scoring unitaire, page détaillée modulable |
| Suivi quotidien | Vue portefeuille, historique scores, re-scoring |
| Gestion watchlist | CRUD watchlist, scoring batch, transfert vers portefeuille |

## Domain-Specific Requirements

### Contraintes Données Financières
- Yahoo Finance peut être indisponible ou retourner des données incomplètes
- Rate limiting sur yfinance — retry nécessaire
- Calculs de scoring reproductibles et cohérents

### Risques Domaine
- Données obsolètes si le scoring n'est pas rafraîchi
- Tickers internationaux avec 30+ formats de bourses
- Yahoo Finance API non-officielle — risque de changement sans préavis

## Web App Specific Requirements

### Architecture
- MPA (Multi Page Application) Flask + Jinja2 templates
- Usage local, desktop-first, mono-utilisateur au MVP
- JavaScript vanilla pour la modularité (drag & drop via SortableJS)
- Pas de framework JS lourd — simplicité privilégiée
- Rafraîchissement manuel (pas de WebSocket/temps réel)

### Browser Support
- Chrome (principal), Firefox/Edge (compatible par défaut)

### Implementation
- Templates Jinja2 avec layout de base héritable
- Static files (CSS/JS) pour styling et interactivité
- Architecture prête pour authentification future
- Pas de SEO requis

## Functional Requirements

### Gestion de la Watchlist

- FR1: L'utilisateur peut ajouter un ticker à sa watchlist
- FR2: L'utilisateur peut supprimer un ticker de sa watchlist
- FR3: L'utilisateur peut visualiser sa watchlist sous forme de liste
- FR4: L'utilisateur peut rechercher un ticker par symbole (30+ bourses)

### Gestion du Portefeuille

- FR5: L'utilisateur peut ajouter une action à son portefeuille
- FR6: L'utilisateur peut supprimer une action de son portefeuille
- FR7: L'utilisateur peut visualiser son portefeuille avec les scores associés
- FR8: L'utilisateur peut transférer une action de la watchlist vers le portefeuille

### Scoring

- FR9: L'utilisateur peut déclencher le scoring d'une action individuelle
- FR10: L'utilisateur peut déclencher le scoring batch de sa watchlist
- FR11: Le système calcule un score potentiel (0-100) basé sur fondamentaux et techniques
- FR12: Le système calcule un score de confiance basé sur la complétude des données
- FR13: Le système génère un classement d'importance des métriques financières

### Historique des Scores

- FR14: Le système enregistre chaque score généré avec sa date
- FR15: L'utilisateur peut consulter l'historique des scores d'une action
- FR16: L'utilisateur peut visualiser l'évolution du score dans le temps

### Page Détaillée Entreprise

- FR17: L'utilisateur peut accéder à une page détaillée par entreprise
- FR18: L'utilisateur peut voir le score et son détail (métriques contributives)
- FR19: L'utilisateur peut voir les fondamentaux (P/E, EV/EBITDA, ROE, CAGR, etc.)
- FR20: L'utilisateur peut voir les indicateurs techniques (RSI, SMA 50/200, momentum)
- FR21: L'utilisateur peut voir les informations d'identité (nom, bourse, capitalisation)
- FR22: L'utilisateur peut réorganiser les sections par drag & drop
- FR23: Le système sauvegarde la disposition personnalisée des sections
- FR24: L'utilisateur peut afficher ou masquer des sections

### Données Financières

- FR25: Le système récupère prix et identité depuis Yahoo Finance
- FR26: Le système récupère les fondamentaux financiers depuis Yahoo Finance
- FR27: Le système calcule les indicateurs techniques (RSI, SMA, momentum)
- FR28: Le système gère les erreurs de récupération avec message utilisateur clair
- FR29: Le système normalise les tickers internationaux (30+ formats)

## Non-Functional Requirements

### Performance
- Scoring unitaire < 5 secondes
- Chargement de page < 2 secondes
- Scoring batch en parallèle (ThreadPoolExecutor)
- Affichage page détaillée sans délai perceptible

### Intégration
- Gestion indisponibilité Yahoo Finance sans crash
- Retry (max 3 tentatives) en cas d'échec réseau
- Mode dégradé si données partiellement indisponibles
- Support tickers 30+ bourses sans configuration

### Maintenabilité
- Backend (scoring, providers, watchlist) découplé du UI Flask
- Architecture extensible pour authentification future
- Stockage JSON migrable vers base de données

## Risk Mitigation

| Risque | Mitigation |
|--------|-----------|
| yfinance instable | Retry, fallback gracieux, message utilisateur |
| Drag & drop complexe | SortableJS (librairie légère éprouvée) |
| Projet solo | MVP lean, itérations courtes |
| Yahoo Finance API change | Abstraction provider, remplacement facile |

