# Monétisation — MyTrader

## Proposition de valeur (9€/mois)

Un screener qui score automatiquement des centaines d'actions (fundamentals + technicals en un chiffre) + des alertes en temps réel quand une opportunité atteint tes critères — sans avoir à ouvrir Bloomberg ou passer 1h sur Yahoo Finance.

---

## Modèle Freemium

| | Gratuit | Premium — ?€/mois |
|---|---|---|
| Analyses | 5 tickers/jour | Illimité |
| Score | Score global uniquement (ex: 74/100) | Score détaillé (fundamentals, momentum, technicals) |
| Screener | Accès lecture, tri par score | Filtres combinés (RSI, momentum, secteur, score min) |
| Watchlist | 5 tickers max | Illimitée |
| Alertes | Non | Oui (RSI, score, momentum) |
| Historique des scores | Non | Oui (évolution dans le temps) |
| Export | Non | PDF + CSV |
| Données | Délai 24h (batch nocturne) | Refresh à la demande (intraday) |

### Logique de conversion

Le gratuit est assez utile pour accrocher, mais la limite de 5 analyses/jour + pas d'alertes + pas de détail du score pousse naturellement vers le premium dès que l'utilisateur est sérieux.

---

## Détail : Gratuit vs Premium sur les données

- **Gratuit** : les cards sont régénérées une fois toutes les 24h via un scheduled job nocturne. Fondamentaux (P/E, marges, market cap) mis à jour en batch.
- **Premium** : refresh à la demande. Données intraday pour le prix et les technicals (RSI, momentum recalculé sur le cours live).

En pratique avec le stack actuel (yfinance) : la différence réelle est **refresh on-demand vs batch nocturne**.

---

## Features prioritaires pour les clients

1. **Score propriétaire** — le vrai différenciateur. Un score 0-100 qui agrège fundamentals + technicals + momentum en un seul chiffre actionnable. Aucun outil gratuit ne propose ca.
2. **Alertes** — cree l'habitude quotidienne, reduit le churn. Un client qui a configure des alertes revient chaque jour.
3. **Card detail par ticker** — remplace 30 min de recherche manuelle : score detaille, RSI, momentum, valorisation (P/E, EV/EBITDA), marge brute, tout en un endroit.

## Features secondaires (hors pitch principal)

- Historique des scores : utile mais trop technique pour onboarder rapidement
- Bitcoin Signal Analyzer : niche, a proposer en add-on separe
- Newsletter : interessant mais secondaire
