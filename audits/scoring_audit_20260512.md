# Audit décalages scoring AlphaBrief — 2026-05-12

## TL;DR

**Cause racine identifiée :** combinaison d'un bug de *cache poisoning* (fundamentals vides cachés 24h) et d'une dégradation FMP (HTTP 402 Payment Required).

**Impact :** 27 / 34 tickers (79 %) de la watchlist active ont leurs scores artificiellement déflatés aujourd'hui (mega-caps US comme AAPL/GOOG/NVDA/AMZN/V tombent à 31-37 au lieu de 55-70 attendus).

**Aucun outlier strict** (< 20 ou > 85) sur la watchlist : la distribution s'étale de 23 (7974.T) à 64 (TSM). Le décalage perçu vient de la compression artificielle du milieu de gamme.

---

## 1. Méthodologie

Comme Supabase n'est pas exposé depuis le VPS (creds dans env du process uniquement), l'audit s'appuie sur la source autoritaire locale :
- `/root/alphabrief/data/mytrader.db` (SQLite : `scores_history`, `card_cache`)
- `/root/alphabrief/data/cache/*.json` (cache FMP par ticker × section, TTL 24 h pour fundamentals)
- `/root/logs/alphabrief-{out,error}.log`

Le schéma Supabase (`ticker_scores` upsert + `score_history` insert) est dual-write — les mêmes scores y sont écrits que dans SQLite local, donc l'analyse est équivalente.

---

## 2. Distribution des scores du jour (2026-05-12)

34 tickers scorés entre 05:00:00 et 05:29:12 UTC (= 07:00 Europe/Paris cron). Aucun score < 20 ni > 85.

| Bucket | Tickers | Count |
|---|---|---|
| > 60 | TSM | 1 |
| 50-60 | KO | 1 |
| 40-49 | MSFT, UBER, NFLX, COST | 4 |
| 30-39 | GOOG, RIO.AX, VLO, NVDA, 285A.T, 8031.T, AAPL, AMZN, SNDK, COHR, ASR, COIN, V, HOOD | 14 |
| 20-29 | 14 autres tickers (SNAP, NU, 1211.HK, 6758.T, INTU, SOFI, VEEV, KLAR, FIG, DPZ, GRAB, ZTS, MELI, 7974.T) | 14 |

Cluster massif au pivot 23-37 → signe distinctif du **scoring sur fundamentals neutralisés**.

---

## 3. Top 10 tickers suspects — décomposition

Reverse-engineering du `factor = 0.5 + 0.5 × confidence / 100` appliqué dans `generator.py:289-293` pour reconstituer les scores bruts pré-confidence.

| Ticker | Score affiché | Fund | Tech | Mom | Conf | Factor | Score brut | Cause probable |
|---|---|---|---|---|---|---|---|---|
| AAPL | 34 | 32 | 36 | 34 | 23 | 0.615 | 55.3 | **Cache fundamentals poison (all-null)** |
| GOOG | 37 | 31 | 36 | 50 | 23 | 0.615 | 60.2 | **Cache fundamentals poison** |
| NVDA | 35 | 31 | 35 | 44 | 23 | 0.615 | 56.9 | **Cache fundamentals poison** |
| AMZN | 34 | 30 | 34 | 43 | 20 | 0.600 | 56.7 | **Cache fundamentals poison** |
| V | 31 | 32 | 32 | 28 | 23 | 0.615 | 50.4 | **Cache fundamentals poison** |
| COIN | 31 | 28 | 32 | 36 | 20 | 0.600 | 51.7 | **Cache fundamentals poison** |
| HOOD | 30 | 28 | 27 | 37 | 20 | 0.600 | 50.0 | **Cache fundamentals poison** |
| INTU | 26 | 30 | 31 | 11 | 23 | 0.615 | 42.3 | **Cache poison + mom_12m faible réel** |
| VEEV | 25 | 29 | 30 | 12 | 20 | 0.600 | 41.7 | **Cache poison + mom faible réel** |
| KLAR | 25 | 28 | 38 | 8 | 18 | 0.590 | 42.4 | **Cache poison + mom faible (small-cap récente)** |

**Lecture :** pour chaque ligne, `Fund` ≈ 28-32 alors que les fundamentals dans le cache sont *tous null*. Ce score ne reflète **pas** la qualité réelle de l'entreprise — il reflète la valeur neutre par défaut de `score_linear` (`default=50.0` dans `potential.py:20`) multipliée par le facteur de confiance bas (~0.60).

À titre de comparaison, MSFT (qui a un cache fundamentals complet) affiche Fund=61 pour Confidence 86, soit raw Fund=65.6 — un signal réel d'entreprise de qualité.

---

## 4. Cause racine #1 — Cache poisoning de fundamentals vides

### Mécanisme

```python
# /root/alphabrief/core/generator.py:165-171
def _fetch_fundamentals():
    cached = _cache.load(ticker, "fundamentals")
    if cached:                                # ← dict non vide mais all-null = truthy
        return cached                         # ← retour silencieux d'un payload poison
    data = fetch_core_fundamentals(ticker)
    _cache.save(ticker, "fundamentals", data) # ← cache sans validation du contenu
    return data
```

```python
# /root/alphabrief/core/providers/fundamentals_yf.py:36-93
def fetch_core_fundamentals(ticker):
    income  = fmp_get("income-statement", ...)   # peut renvoyer [] sans erreur HTTP
    balance = fmp_get("balance-sheet-statement", ...)
    ...
    inc: List[Dict] = income if isinstance(income, list) else []  # liste vide acceptée
    inc0: Dict = inc[0] if inc else {}                            # dict vide accepté
    out = {
      "financials": { tous les champs initialisés à None },
      "valuation":  { tous les champs initialisés à None },
      "source": "fmp",                                            # ← drapeau toujours présent
    }
    # tout le reste de la fonction ne remplace les None que si l'API a renvoyé des données
    return out                                                    # all-null mais source="fmp"
```

### Diagnostic empirique

| Métrique | Valeur |
|---|---|
| Caches fundamentals présents | 34 |
| Caches **0 / 29 champs valides** ("poison") | **27** (79 %) |
| Caches partiels (SNAP, 10 / 29) | 1 |
| Caches complets (26+/30) | 6 (MSFT, NFLX, COST, TSM, KO, UBER) |

Tickers contaminés :
```
1211.HK, 285A.T, 6758.T, 7974.T, 8031.T, AAPL, AMZN, ASR, COHR, COIN,
DPZ, FIG, GOOG, GRAB, HOOD, INTU, KLAR, MELI, NU, NVDA, RIO.AX, SNDK,
SOFI, V, VEEV, VLO, ZTS
```

### TTL trop long pour un échec silencieux

```python
# /root/alphabrief/utils/cache.py:16-22
SECTION_TTL: Dict[str, float] = {
    "fundamentals": 24.0,   # ← un échec FMP bloque le re-fetch pendant 24h complètes
    "identity":     6.0,
    "technicals":   1.0,
    "llm":          48.0,
    "momentum":     2.0,
}
```

Une fois qu'un cache fundamentals est créé (même vide), il sera servi 24 h sans aucune tentative de rafraîchissement → cascade quotidienne de scores dégradés tant que personne n'invalide manuellement.

---

## 5. Cause racine #2 — Dégradation API FMP (HTTP 402)

### Signal direct

`/root/logs/alphabrief-error.log` — scoring de ce matin 2026-05-12 :

```
05:17:53 WARNING fmp_request_error endpoint=quote symbol=GRAB
  "402 Client Error: Payment Required for url:
   https://financialmodelingprep.com/stable/quote?symbol=GRAB&apikey=rB9ziwhSnXsAYvHOdihZgUOLdUjtWf3C"
```

⚠️ **La clé FMP est exposée en clair dans le log d'erreur.** Elle est journalée à chaque retry du `_BACKOFF_STEPS`. À régénérer côté FMP et à scrubber des logs avant rotation.

### Volumétrie des erreurs FMP (historique cumulé)

| Endpoint | Nombre d'erreurs |
|---|---|
| `quote` | 1 565 |
| `income-statement` | 649 |
| `cash-flow-statement` | 646 |
| `balance-sheet-statement` | 645 |
| `ratios-ttm` | 636 |
| `key-metrics-ttm` | 617 |
| `enterprise-values` | 614 |
| `profile` | 418 |

Le retry policy (4 tentatives × 4 endpoints) amplifie : un seul ticker en échec → ~28 lignes de log. La majorité des fundamentals échouent silencieusement (FMP renvoie `[]` au lieu de 402 sur certains endpoints non-couverts par le plan, d'où l'absence d'erreur visible et la création de caches poison).

### Pattern temporel 2026-05-11

Sur le scoring run du 2026-05-11 (logs `ticker_scored`) :

- 05:01–05:48 (7 tickers OK avec confidence ≥ 79) : MSFT, NFLX, COST, TSM, KO, UBER — *avant le seuil de quota*
- 06:05 : SNAP `confidence: 43` — partiellement servi (10 champs sur 29)
- 06:18 → 09:11 (27 tickers) : `confidence: 12-23` — fundamentals tous null mais log `status: ok`

→ FMP a apparemment limité l'accès après les premières requêtes du matin (quota Starter de 300 req/min déjà saturé par 7 tickers × 7 endpoints = 49 req initiales, mais le quota journalier ou la couverture du plan est probablement la vraie cause).

---

## 6. Causes secondaires (point 3 de la mission)

| Source d'erreur classique | État | Détail |
|---|---|---|
| Valeurs `None` → 0 plombant le score | **Non** | `score_linear` retourne `default=50.0` (neutre, pas pénalisant directement) |
| `None` → 50 (double-effet pénalisant) | **Oui (secondaire)** | Combiné au confidence multiplier 0.6, un fund neutre devient un score affiché 30 |
| Données FMP périmées (timestamp) | **Oui (critique)** | TTL 24h trop long, pas de validation du contenu |
| Normalisation min/max univers restreint | Non concerné | Tous les sous-scores sont calibrés par valeurs absolues (P/E < 15 → 80, etc.), pas par percentiles |
| Mélange devises/unités | **À vérifier** | `_safe_pct` multiplie par 100 — si FMP renvoie déjà du %, double comptage possible. Sur MSFT le gross_margin=68.8 est plausible donc OK pour US tickers. Tickers internationaux non vérifiables car cache poison |
| Bornes mal calibrées | Non | Calibration par secteur dans `*_score_sector_aware` fonctions, semble cohérente |
| Division par zéro masquée | Non | `score_linear` clamp et `to_float` retournent `None` proprement |
| Cache local désynchronisé | **OUI — cause #1** | Voir §4 |

---

## 7. Cohérence temporelle (point 4 de la mission)

| Vérif | État | Détail |
|---|---|---|
| Momentum sur prix ajustés | Partiellement | `compute_relative_momentum` (momentum.py:46) passe explicitement `auto_adjust=True`. `compute_momentum_12m` et `compute_technicals` utilisent `yf.Ticker(t).history(period=...)` sans le préciser. yfinance ≥ 0.2.x utilise `auto_adjust=True` par défaut, donc OK en pratique, mais c'est fragile si la dépendance est downgradée. |
| Fundamentals annual vs TTM | **Mix** | `income/balance/cashflow` : `period="annual" limit=4` → utilisés pour CAGR/YoY. `ratios-ttm` et `key-metrics-ttm` : TTM → utilisés pour P/E, FCF yield. Cohérent en intention. |
| Scheduler tourne sans erreur | Oui | PM2 alphabrief online 2D, 20 restarts cumulés. Scoring run de ce matin a bouclé toute la watchlist en ~30 min. |

---

## 8. Recommandations de fix (à valider avant application)

### Fix #1 — Refuser de cacher un payload fundamentals vide (priorité haute)

```python
# /root/alphabrief/core/generator.py:165-171
def _fetch_fundamentals():
    cached = _cache.load(ticker, "fundamentals")
    if cached and _has_useful_fundamentals(cached):
        return cached
    data = fetch_core_fundamentals(ticker)
    if _has_useful_fundamentals(data):
        _cache.save(ticker, "fundamentals", data)
    return data

def _has_useful_fundamentals(payload: dict) -> bool:
    """Au moins 3 champs financials/valuation non-null pour considérer le payload utile."""
    fin = payload.get("financials", {}) if payload else {}
    val = payload.get("valuation", {}) if payload else {}
    n_valid = sum(1 for v in {**fin, **val}.values() if v is not None)
    return n_valid >= 3
```

### Fix #2 — Invalider les caches poison existants (one-shot)

```bash
python3 -c "
import json
from pathlib import Path
for p in Path('/root/alphabrief/data/cache').glob('*_fundamentals.json'):
    d = json.loads(p.read_text())['data']
    fin = d.get('financials', {})
    val = d.get('valuation', {})
    n_valid = sum(1 for v in {**fin, **val}.values() if v is not None)
    if n_valid == 0:
        p.unlink()
        print('purged', p.name)
"
```

### Fix #3 — TTL plus court ou TTL contextuel (priorité moyenne)

Réduire `fundamentals` TTL de 24 h → 6 h, OU implémenter un TTL différencié : 24 h sur succès, 1 h sur échec (cache négatif).

### Fix #4 — Scrubber la clé FMP des logs (priorité haute, hygiène)

```python
# /root/alphabrief/core/providers/fmp_client.py:147
"error": str(e).replace(_API_KEY, "***"),
```

Et régénérer la clé `rB9ziwhSnXsAYvHOdihZgUOLdUjtWf3C` côté FMP : elle est leakée dans les logs.

### Fix #5 — Détacher confidence du multiplier (à débattre)

L'effet `factor = 0.5 + 0.5 × confidence / 100` divise par 2 les scores quand confidence < 5 %. Or `score_linear` retourne déjà `default=50` (neutre) sur données manquantes. Le multiplier additionnel **pénalise deux fois** l'absence de données. À discuter : soit garder le multiplier mais relever le default de `score_linear` de 50 → 0 (équivalent stricte « no data = no score »), soit retirer le multiplier et garder `default=50`.

### Fix #6 — Plan FMP

Vérifier le statut du plan FMP et la couverture des tickers internationaux (1211.HK, 285A.T, 6758.T, 7974.T, 8031.T, RIO.AX) qui semblent hors-périmètre. Soit upgrader le plan, soit retirer ces tickers de la watchlist, soit prévoir un fallback yfinance pour fundamentals internationaux.

---

## 9. Script de reproduction

Voir `/root/alphabrief/audits/reproduce_scoring_audit.py`.

Lancer : `python3 /root/alphabrief/audits/reproduce_scoring_audit.py`

Sortie attendue : table des 34 tickers actuels × (score affiché, sous-scores, confidence, factor, score brut reconstruit, validité du cache fundamentals).
