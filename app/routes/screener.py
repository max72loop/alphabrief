from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, render_template, current_app

bp = Blueprint('screener', __name__, url_prefix='/screener')

_CARDS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cards"


def _fmt(value: Optional[float], decimals: int = 1) -> Optional[str]:
    if value is None:
        return None
    return f"{value:.{decimals}f}"


def _load_rows() -> List[Dict[str, Any]]:
    rows = []
    if not _CARDS_DIR.exists():
        return rows

    for path in sorted(_CARDS_DIR.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        identity = card.get("identity", {})
        financials = card.get("financials", {})
        valuation = card.get("valuation", {})
        market = card.get("market", {})
        technicals = card.get("technicals", {})
        scores = card.get("scores", {})

        score = scores.get("potential_score")
        confidence = scores.get("confidence_score")
        rsi = technicals.get("rsi_14")
        mom_3m = market.get("momentum_3m")
        mom_12m = market.get("momentum_12m")
        pe = valuation.get("pe_ttm")
        ev_ebitda = valuation.get("ev_ebitda_ttm")
        gross_margin = financials.get("gross_margin")
        fcf_margin = financials.get("fcf_margin")
        market_cap = identity.get("market_cap")

        rows.append({
            "ticker": identity.get("ticker", path.stem),
            "name": identity.get("name", ""),
            "sector": identity.get("sector", ""),
            "currency": identity.get("currency", ""),
            "as_of": card.get("as_of", ""),
            "score": score,
            "score_label": scores.get("score_label", ""),
            "confidence": confidence,
            "rsi": _fmt(rsi),
            "mom_3m": _fmt(mom_3m),
            "mom_12m": _fmt(mom_12m),
            "pe": _fmt(pe, 1),
            "ev_ebitda": _fmt(ev_ebitda, 1),
            "gross_margin": _fmt(gross_margin, 1),
            "fcf_margin": _fmt(fcf_margin, 1),
            "market_cap_b": _fmt(market_cap / 1e9, 1) if market_cap else None,
            # raw numerics for JS sorting/filtering
            "_score": score or -1,
            "_rsi": rsi or 0,
            "_mom_3m": mom_3m or 0,
            "_pe": pe or 0,
        })

    rows.sort(key=lambda r: r["_score"], reverse=True)
    return rows


@bp.route("/")
def index():
    rows = _load_rows()
    sectors = sorted({r["sector"] for r in rows if r["sector"]})
    return render_template("screener.html", rows=rows, sectors=sectors)
