from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, render_template, request

bp = Blueprint('compare', __name__, url_prefix='/compare')

_CARDS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cards"


def _load_card(ticker: str) -> Optional[Dict[str, Any]]:
    path = _CARDS_DIR / f"{ticker.upper()}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _all_tickers() -> List[str]:
    if not _CARDS_DIR.exists():
        return []
    return sorted(p.stem for p in _CARDS_DIR.glob("*.json"))


def _fmt(value: Optional[float], decimals: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}{suffix}"


def _winner(a: Optional[float], b: Optional[float], higher_is_better: bool = True) -> Tuple[bool, bool]:
    """Return (a_wins, b_wins). Both False if equal or missing."""
    if a is None or b is None:
        return False, False
    if a == b:
        return False, False
    if higher_is_better:
        return a > b, a < b
    else:
        return a < b, a > b


def _build_metrics(card: Dict[str, Any]) -> Dict[str, Any]:
    fin = card.get("financials", {})
    val = card.get("valuation", {})
    mkt = card.get("market", {})
    tech = card.get("technicals", {})
    scores = card.get("scores", {})
    ident = card.get("identity", {})
    return {
        # scores
        "potential_score": scores.get("potential_score"),
        "confidence_score": scores.get("confidence_score"),
        # identity
        "market_cap": ident.get("market_cap"),
        # quality
        "gross_margin": fin.get("gross_margin"),
        "ebit_margin": fin.get("ebit_margin"),
        "fcf_margin": fin.get("fcf_margin"),
        "roe": fin.get("roe"),
        "net_debt_to_ebitda": fin.get("net_debt_to_ebitda"),
        "interest_coverage": fin.get("interest_coverage"),
        # growth
        "revenue_cagr_3y": fin.get("revenue_cagr_3y"),
        # valuation
        "pe_ttm": val.get("pe_ttm"),
        "forward_pe": val.get("forward_pe"),
        "ev_ebitda_ttm": val.get("ev_ebitda_ttm"),
        "fcf_yield_ttm": val.get("fcf_yield_ttm"),
        "peg_ratio": val.get("peg_ratio"),
        "pb_ratio": val.get("pb_ratio"),
        # market
        "momentum_12m": mkt.get("momentum_12m"),
        "momentum_3m": mkt.get("momentum_3m"),
        "dividend_yield": mkt.get("dividend_yield"),
        "beta": mkt.get("beta"),
        "analyst_target_mean": mkt.get("analyst_target_mean"),
        # technical
        "rsi_14": tech.get("rsi_14"),
        "volatility_1y": tech.get("volatility_1y"),
        "max_drawdown_1y": tech.get("max_drawdown_1y"),
    }


# Each row: (label, key, higher_is_better, decimals, suffix)
METRIC_ROWS = [
    # --- Score ---
    ("Score potentiel",     "potential_score",     True,  0, ""),
    ("Confiance",           "confidence_score",    True,  0, "%"),
    # --- Quality ---
    ("Marge brute",         "gross_margin",        True,  1, "%"),
    ("Marge EBIT",          "ebit_margin",         True,  1, "%"),
    ("Marge FCF",           "fcf_margin",          True,  1, "%"),
    ("ROE",                 "roe",                 True,  1, "%"),
    ("Dette nette / EBITDA","net_debt_to_ebitda",  False, 2, "x"),
    ("Couverture intérêts", "interest_coverage",   True,  1, "x"),
    # --- Growth ---
    ("Rev CAGR 3Y",         "revenue_cagr_3y",     True,  1, "%"),
    # --- Value ---
    ("P/E TTM",             "pe_ttm",              False, 1, "x"),
    ("Forward P/E",         "forward_pe",          False, 1, "x"),
    ("EV/EBITDA",           "ev_ebitda_ttm",       False, 1, "x"),
    ("FCF Yield TTM",       "fcf_yield_ttm",       True,  1, "%"),
    ("PEG Ratio",           "peg_ratio",           False, 2, "x"),
    ("P/B Ratio",           "pb_ratio",            False, 2, "x"),
    # --- Market ---
    ("Momentum 12M",        "momentum_12m",        True,  1, "%"),
    ("Momentum 3M",         "momentum_3m",         True,  1, "%"),
    ("Dividend Yield",      "dividend_yield",      True,  2, "%"),
    ("Beta",                "beta",                False, 2, ""),
    ("Cible analystes",     "analyst_target_mean", True,  2, ""),
    # --- Technical ---
    ("RSI 14",              "rsi_14",              None,  1, ""),   # no winner (contextual)
    ("Volatilité 1Y",       "volatility_1y",       False, 1, "%"),
    ("Max Drawdown 1Y",     "max_drawdown_1y",     False, 1, "%"),
]

SECTION_HEADERS = {
    "Score potentiel":      "Score",
    "Marge brute":          "Qualité",
    "Rev CAGR 3Y":          "Croissance",
    "P/E TTM":              "Valorisation",
    "Momentum 12M":         "Marché",
    "RSI 14":               "Technique",
}


@bp.route("/")
def index():
    tickers = _all_tickers()
    ticker_a = request.args.get("a", "").upper().strip()
    ticker_b = request.args.get("b", "").upper().strip()

    card_a = _load_card(ticker_a) if ticker_a else None
    card_b = _load_card(ticker_b) if ticker_b else None

    metrics_a = _build_metrics(card_a) if card_a else {}
    metrics_b = _build_metrics(card_b) if card_b else {}

    rows = []
    for label, key, higher_is_better, decimals, suffix in METRIC_ROWS:
        val_a = metrics_a.get(key)
        val_b = metrics_b.get(key)

        if higher_is_better is None:
            win_a, win_b = False, False
        else:
            win_a, win_b = _winner(val_a, val_b, higher_is_better)

        section_header = SECTION_HEADERS.get(label)
        rows.append({
            "label": label,
            "section_header": section_header,
            "val_a": _fmt(val_a, decimals, suffix),
            "val_b": _fmt(val_b, decimals, suffix),
            "win_a": win_a,
            "win_b": win_b,
            "missing_a": val_a is None,
            "missing_b": val_b is None,
        })

    # Count wins
    wins_a = sum(1 for r in rows if r["win_a"])
    wins_b = sum(1 for r in rows if r["win_b"])

    meta_a = card_a.get("identity", {}) if card_a else {}
    meta_b = card_b.get("identity", {}) if card_b else {}

    return render_template(
        "compare.html",
        tickers=tickers,
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        card_a=card_a,
        card_b=card_b,
        meta_a=meta_a,
        meta_b=meta_b,
        rows=rows,
        wins_a=wins_a,
        wins_b=wins_b,
    )
