# AlphaBrief — Stratégie Tarifaire

## 📊 Vue d'ensemble

**AlphaBrief** = Screener d'actions avec scoring automatique + features avancées (alertes, portfolio, cycle detection, Bitcoin analyzer).

**Objectif:** Commencer simple à 4.99€, avec bundles optionnels pour monétiser les users avancés.

---

## 🎯 Architecture Tarifaire

### Tier 1: **SCOUT** — 4.99€/mois (Base)

**Cible:** Débutants / curieux

| Feature | Scout | 
|---------|-------|
| **Analyse de tickers** | 5 tickers/jour | 
| **Score** | Score global uniquement (0-100) | 
| **Screener** | Oui, mais filtre simple (secteur, score min) | 
| **Watchlist** | 5 tickers max | 
| **Alertes** | ❌ Non | 
| **Portfolio** | ❌ Non | 
| **Comparaison** | ❌ Non | 
| **Cycle Detection** | ❌ Non | 
| **Bitcoin Analyzer** | ❌ Non | 
| **Refresh données** | Batch nocturne (24h) | 
| **Export** | ❌ Non | 
| **Support** | Email (48h) | 

**Pitch:** "Commencez à screener les stocks en 30 secondes. Score automatique, sans Bloomberg."

**Friction → Conversion:** 
- 5 analyses/jour suffisent pour accrocher
- Mais dès qu'on vent plus = besoin des bundles
- Pas d'alertes = pas d'habitude quotidienne = faible rétention

---

### Bundle A: **PRO SCREENER** — +2.99€/mois (7.98€ total)

**Cible:** Investisseurs passifs / screeners occasionnels

| Feature | Scout | +Pro Screener |
|---------|-------|---|
| **Analyses/jour** | 5 | Illimité | 
| **Score détaillé** | ❌ | ✅ (fundamentals + technicals + momentum) | 
| **Screener avancé** | Basique | ✅ RSI, momentum 3m/12m, marges, P/E, EV/EBITDA |
| **Watchlist** | 5 | 50 |
| **Alertes** | ❌ | ✅ (score, RSI, momentum) |
| **Historique scores** | ❌ | ✅ (évolution 12 mois) |

**Pitch:** "Alertes push + filtres puissants = gagnez 1h par jour de research."

**Valeur:** Remplace 30-40€/mois d'autres screeners (Finviz, TradingView light)

---

### Bundle B: **TRADER TOOLS** — +3.99€/mois (8.98€ total)

**Cible:** Traders actifs / day-traders

| Feature | +Trader Tools |
|---------|---|
| **Comparaison ticker** | ✅ (side-by-side: scores, financials, technicals) |
| **Cycle Detection** | ✅ (phase du cycle économique + recommendation par secteur) |
| **Refresh intraday** | ✅ (refresh à la demande, données live) |
| **Bitcoin Signal Analyzer** | ✅ (momentum BTC, fear/greed index correlation) |
| **Alertes avancées** | ✅ (crossover RSI, momentum reversal) |
| **Export** | ✅ (CSV + PDF des analyses) |

**Pitch:** "Cycle detection + Bitcoin signals = anticipez les rotations de secteurs."

**Valeur:** Remplace 50-100€/mois de tools spécialisés

---

### Bundle C: **PORTFOLIO PRO** — +2.99€/mois (7.98€ total, stack avec autres)

**Cible:** Investisseurs qui trackent un portefeuille

| Feature | +Portfolio Pro |
|---------|---|
| **Portfolio tracking** | ✅ (position sizing, allocation %) |
| **Performance tracking** | ✅ (gains/pertes, % return) |
| **Rebalancing alerts** | ✅ (quand allocation dérrive >5%) |
| **Sector exposure** | ✅ (voir votre exposition par secteur) |
| **Individual stock alerts** | ✅ (alerte si une position devient bearish) |

**Pitch:** "Trackez votre portefeuille sans Excel."

---

## 📈 Combinaisons possibles

| Combo | Price | Cible | Valeur |
|-------|-------|-------|--------|
| **Scout seul** | 4.99€ | Gratuit+ addict | Découverte |
| Scout + Pro Screener | 7.98€ | Investisseur passif | -80% vs Finviz |
| Scout + Trader Tools | 8.98€ | Day-trader | Cycle + Bitcoin |
| Scout + Portfolio Pro | 7.98€ | Investisseur | Suivi simple |
| **Scout + Pro + Trader** | 11.97€ | Power user | Full toolkit |
| Scout + Pro + Portfolio | 10.97€ | Investisseur sérieux | Screener + portfolio |
| **Scout + Tous** | 14.97€ | Ultimate (lte churn) | Everything |

---

## 🎪 Stratégie d'activation & conversion

### Phase 1: Free trial
- **Gratuit 7 jours** : Accès Pro Screener complet
- **Push principal:** "Essayez les alertes en temps réel"

### Phase 2: Onboarding
- Après 7 jours → "Vous avez reçu 23 alertes cette semaine"
- **CTA:** "Gardez l'accès aux alertes" (7.98€/mois)

### Phase 3: Upsell intelligent
- Une fois Scout + Pro → Propose Trader Tools si l'utilisateur:
  - Fait des comparaisons entre tickers (comportement détecté)
  - A plus de 10 tickers en watchlist
- Une fois Scout → Propose Portfolio si l'utilisateur:
  - Ajoute beaucoup de tickers à la watchlist (probable qu'il track un portfolio)

### Phase 4: Retention
- **Win-back email** pour churn: "Vous aviez 5 alertes qui vous attendaient"
- **Annual discount** (10% off) pour réduire churn

---

## 💰 Economics & Unit Economics

**Hypothèses:**
- **CAC (Cost of Acquisition):** 15€ (via Facebook/Google ads)
- **MRR target:** 20% conversion from free tier
- **LTV:** 12-month average

| Scenario | MRR/User | CAC Payback | LTV (12m) |
|----------|----------|------------|----------|
| Scout only | 4.99€ | 3 mois | 59.88€ |
| Scout → Pro (month 2) | 7.98€ | 1.9 mois | 95.76€ |
| Scout → Pro + Trader (month 3) | 11.97€ | 1.3 mois | 143.64€ |

**Objectif:** Moyen 8-10€/user = LTV 100€+ sur 12 mois.

---

## 🔄 Implémentation

### Phase 1 (Semaine 1-2): Lancer Scout (4.99€)
- Limiter à 5 analyses/jour
- Score global uniquement (pas de détails)
- Watchlist limitée à 5

### Phase 2 (Semaine 3-4): Ajouter Pro Screener
- Feature flag pour unlock alertes + screener détaillé
- Modifier les routes pour vérifier le tier

### Phase 3 (Semaine 5-6): Ajouter Trader Tools
- Toggle pour cycle detection + comparaison
- Option Bitcoin analyzer

### Phase 4 (Semaine 7+): Portfolio Pro
- Implémentation du portfolio tracking

---

## 🛠️ Technical Implementation Notes

### Feature Flags (à implémenter)
```python
class UserTier:
    SCOUT = "scout"  # 4.99€
    TIERS = {
        "scout": {"analyses_per_day": 5, "watchlist_max": 5, ...},
        "pro_screener": {"analyses_per_day": None, "alerts": True, ...},
        "trader_tools": {"cycle_detection": True, "bitcoin": True, ...},
        "portfolio_pro": {"portfolio_tracking": True, ...}
    }
```

### Routes à protéger
- `/screener` → Vérifier `pro_screener` ou plus
- `/bitcoin` → Vérifier `trader_tools`
- `/alerts/*` → Vérifier `pro_screener` ou plus
- `/portfolio/*` → Vérifier `portfolio_pro`
- `/compare` → Vérifier `trader_tools`
- `/cycle` → Vérifier `trader_tools`

### Payement
- Intégrer Stripe pour les subscriptions
- Webhook pour handle upgrades/downgrades
- Usage limits (ex: check `analyses_today()` < max avant de scorer)

---

## 📊 Metrics à tracker

- % users who upgrade from Scout
- Average LTV by tier combo
- Churn rate by tier (Portfolio Pro = lower churn likely)
- Feature adoption (qui utilise alertes, cycle detection, etc.)
- Revenue per user (ARPU)

---

## Pitch pour Max

**TL;DR:**
- **4.99€ base** = accessible, crée une habitude (alertes)
- **Bundles +2.99€ à +3.99€** = cible différents use cases
- **Target mix:** Scout + Pro Screener (7.98€) par défaut, puis upsells
- **LTV potential:** 100€+ sur 12 mois avec moyenne 8-10€/user

À implémenter par priority: Pro Screener (alertes = clé du churn), puis Trader Tools (audience spécialisée), puis Portfolio Pro (rétention).
