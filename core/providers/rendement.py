"""Données de la prime de rendement et de la dilution (2026-10-27).

Trois lectures, FMP d'abord, yfinance en repli, cache 24 h (section
`rendement` de utils/cache.py) — un refresh quotidien suffit, et le coût FMP
reste de 2 appels par ticker et par jour + 1 pour le taux :

  · taux_10y()                → treasury-rates (champ year10), repli ^TNX
  · croissance_consensus(t)   → analyst-estimates annuel, repli revenue_estimate
  · actions_trimestrielles(t) → income-statement trimestriel, champ
                                weightedAverageShsOutDil, repli
                                quarterly_income_stmt « Diluted Average Shares »

Le plan FMP ne couvre que les cotations US : un symbole étranger répond 402
« Premium », que fmp_client traite symbole par symbole (sans couper FMP pour
les autres) — on retombe alors sur yfinance.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.providers.fmp_client import fmp_get
from utils import cache as _cache

logger = logging.getLogger(__name__)

_TAUX_KEY = "_US10Y"


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


# ── Taux sans risque ────────────────────────────────────────────────────────
def _taux_fmp() -> Optional[Dict[str, Any]]:
    fin = date.today()
    rows = fmp_get("treasury-rates", {"from": (fin - timedelta(days=10)).isoformat(), "to": fin.isoformat()})
    if not isinstance(rows, list):
        return None
    for r in sorted(rows, key=lambda r: r.get("date") or "", reverse=True):
        v = _num(r.get("year10"))
        if v is not None:
            return {"taux": v, "date": r.get("date"), "source": "fmp"}
    return None


def _taux_yf() -> Optional[Dict[str, Any]]:
    try:
        import yfinance as yf
        h = yf.Ticker("^TNX").history(period="10d")
        if h is None or h.empty:
            return None
        v = _num(h["Close"].dropna().iloc[-1])
        return {"taux": v, "date": str(h.index[-1].date()), "source": "yfinance"} if v is not None else None
    except Exception as e:
        logger.warning("taux 10 ans yfinance indisponible : %s", e)
        return None


def taux_10y() -> Optional[Dict[str, Any]]:
    """{taux (en %), date, source}, ou None si aucune source ne répond."""
    cached = _cache.load(_TAUX_KEY, "rendement")
    if cached and cached.get("taux") is not None:
        return cached
    data = _taux_fmp() or _taux_yf()
    if data:
        _cache.save(_TAUX_KEY, "rendement", data)
    return data


# ── Croissance attendue du CA (consensus) ───────────────────────────────────
def croissance_depuis_estimations(rows: List[Dict[str, Any]], aujourd_hui: date) -> Optional[float]:
    """CAGR du CA de l'exercice passé à l'exercice suivant, en %/an.

    `rows` : analyst-estimates FMP (date de clôture d'exercice, revenueAvg).
    L'exercice en cours est le premier qui clôt après aujourd'hui. Sans exercice
    passé dans la réponse, on prend l'exercice en cours → celui d'après+1.
    """
    pts = sorted(
        ((r.get("date") or "", _num(r.get("revenueAvg"))) for r in rows or []),
        key=lambda x: x[0],
    )
    pts = [(d, v) for d, v in pts if d and v is not None and v > 0]
    i0 = next((i for i, (d, _) in enumerate(pts) if d >= aujourd_hui.isoformat()), None)
    if i0 is None:
        return None
    if i0 >= 1 and i0 + 1 < len(pts):
        a, b = pts[i0 - 1][1], pts[i0 + 1][1]
    elif i0 + 2 < len(pts):
        a, b = pts[i0][1], pts[i0 + 2][1]
    else:
        return None
    return ((b / a) ** 0.5 - 1.0) * 100.0


def _croissance_yf(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        est = yf.Ticker(ticker).revenue_estimate
        g0, g1 = _num(est.loc["0y", "growth"]), _num(est.loc["+1y", "growth"])
        if g0 is None or g1 is None:
            return None
        return (((1 + g0) * (1 + g1)) ** 0.5 - 1.0) * 100.0
    except Exception:
        return None


# ── Actions diluées trimestrielles ──────────────────────────────────────────
def _actions_yf(ticker: str) -> tuple[List[Optional[float]], List[str], Optional[str]]:
    """(actions, dates de clôture, devise de publication) — du plus récent au plus ancien."""
    # Deux lectures séparées : un émetteur semestriel (RIO.AX) n'a pas de relevé
    # trimestriel, et la devise de publication doit survivre à cette absence.
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
    except Exception:
        return [], [], None
    try:
        devise = (t.info or {}).get("financialCurrency")
    except Exception:
        devise = None
    try:
        q = t.quarterly_income_stmt
        label = "Diluted Average Shares" if "Diluted Average Shares" in q.index else "Basic Average Shares"
        return [_num(v) for v in q.loc[label].tolist()], [str(c.date()) for c in q.columns], devise
    except Exception:
        return [], [], devise


def change(de: Optional[str], vers: Optional[str]) -> Optional[float]:
    """Cours `de` → `vers` (1 TWD = x USD), yfinance. 1.0 si même devise, None si inconnu."""
    if not de or not vers:
        return None
    if de.upper() == vers.upper():
        return 1.0
    try:
        import yfinance as yf
        h = yf.Ticker(f"{de.upper()}{vers.upper()}=X").history(period="10d")
        return _num(h["Close"].dropna().iloc[-1]) if h is not None and not h.empty else None
    except Exception:
        return None


def _ipo_date(ticker: str) -> Optional[str]:
    # `profile` est déjà demandé par price_identity avec les mêmes paramètres :
    # le cache process de fmp_client le sert sans nouvel appel.
    prof = fmp_get("profile", {"symbol": ticker})
    if isinstance(prof, list) and prof:
        return prof[0].get("ipoDate") or None
    return None


_FORMAT = 3   # version du contenu en cache : un cache d'un format antérieur est ignoré


def fetch_rendement(ticker: str, devise_cotation: Optional[str] = None) -> Dict[str, Any]:
    """Consensus de croissance + série d'actions, pour un ticker. Mis en cache 24 h.

    `devise_cotation` : devise du cours (identity.currency). Si les comptes sont
    publiés dans une autre devise (TSM en TWD, BYD en CNY), `fx_publication`
    porte le cours qui ramène le FCF dans la devise de la capitalisation.
    """
    cached = _cache.load(ticker, "rendement")
    if cached and cached.get("format") == _FORMAT:
        return cached

    out: Dict[str, Any] = {
        "format": _FORMAT, "croissance_ca": None, "croissance_source": None,
        "actions_q": [], "actions_dates": [], "actions_source": None,
        "devise_publication": None, "fx_publication": None, "ipo_date": _ipo_date(ticker),
    }

    est = fmp_get("analyst-estimates", {"symbol": ticker, "period": "annual", "limit": "10"})
    g = croissance_depuis_estimations(est, date.today()) if isinstance(est, list) else None
    if g is not None:
        out.update(croissance_ca=g, croissance_source="fmp")
    else:
        g = _croissance_yf(ticker)
        if g is not None:
            out.update(croissance_ca=g, croissance_source="yfinance")

    inc = fmp_get("income-statement", {"symbol": ticker, "period": "quarter", "limit": "13"})
    if isinstance(inc, list) and inc:
        rows = sorted(inc, key=lambda r: r.get("date") or "", reverse=True)
        out.update(
            actions_q=[_num(r.get("weightedAverageShsOutDil")) for r in rows],
            actions_dates=[r.get("date") for r in rows],
            actions_source="fmp",
            devise_publication=rows[0].get("reportedCurrency"),
        )
    else:
        serie, dates, devise = _actions_yf(ticker)
        if serie:
            out.update(actions_q=serie, actions_dates=dates, actions_source="yfinance")
        out["devise_publication"] = devise

    out["fx_publication"] = change(out["devise_publication"], devise_cotation)
    _cache.save(ticker, "rendement", out)
    return out
