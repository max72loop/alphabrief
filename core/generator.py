from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.providers.price_identity import fetch_identity_and_market
from core.features.momentum import compute_momentum_12m, compute_relative_momentum
from core.features.technicals import compute_technicals
from core.scoring.potential import compute_potential_score
from core.providers.fundamentals_yf import fetch_core_fundamentals
from core.providers.llm_enricher import enrich_with_llm
from core.scoring.importance import build_importance_items
from core.scoring.confidence import compute_confidence_score
from utils import cache as _cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _score_label(score: Optional[int]) -> str:
    if score is None:
        return "N/A"
    if score >= 80:
        return "Exceptionnel"
    if score >= 65:
        return "Fort"
    if score >= 50:
        return "Modéré"
    if score >= 35:
        return "Neutre"
    if score >= 20:
        return "Faible"
    return "À éviter"


def empty_card(ticker: str) -> Dict[str, Any]:
    return {
        "as_of": date.today().isoformat(),
        "identity": {
            "ticker": ticker.upper(),
            "name": "",
            "exchange": "",
            "currency": "",
            "sector": "",
            "industry": "",
            "market_cap": None,
        },
        "business_snapshot": {
            "one_liner": "",
            "segments": [],
            "geographies": [],
            "moat_tags": [],
            "top_competitors": [],
        },
        "financials": {
            "revenue_cagr_3y": None,
            "revenue_yoy_rates": None,
            "ebit_margin": None,
            "gross_margin": None,
            "fcf_margin": None,
            "roe": None,
            "roic": None,
            "net_debt_to_ebitda": None,
            "interest_coverage": None,
            "share_dilution_3y": None,
            "payout_ratio": None,
            "fcf_absolute": None,
            "net_income": None,
            "current_ratio": None,
            "eps_growth": None,
            "net_margin": None,
            "insider_ownership": None,
            "short_interest": None,
            "gross_margin_trend": None,
            "accruals_ratio": None,
            "institutional_ownership": None,
            "altman_z": None,
        },
        "valuation": {
            "pe_ttm": None,
            "ev_ebitda_ttm": None,
            "ev_sales_ttm": None,
            "fcf_yield_ttm": None,
            "pb_ratio": None,
            "price_to_ocf": None,
        },
        "market": {
            "beta": None,
            # FIX M3 (audit 2026-05-13) : champs alignés avec fetch_identity_and_market.
            # `volatility_1y` et `drawdown_1y` retirés d'ici (gardés uniquement dans
            # technicals où ils sont calculés).
            "avg_volume_3m": None,
            "current_price": None,
            "previous_close": None,
            "change_pct": None,
            "volume": None,
            "fifty_two_week_low": None,
            "fifty_two_week_high": None,
            "dividend_yield": None,
            "momentum_1m": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "relative_momentum_1m": None,
            "relative_momentum_3m": None,
            "relative_momentum_12m": None,
            "analyst_target_mean": None,
            "analyst_target_low": None,
            "analyst_target_high": None,
            "analyst_count": None,
            "analyst_recommendation": None,
        },
        "technicals": {
            "rsi_14": None,
            "sma_50": None,
            "sma_200": None,
            "macd_line": None,
            "macd_signal": None,
            "macd_histogram": None,
            "volatility_1y": None,
            "max_drawdown_1y": None,
        },
        "events": {
            "next_earnings_date": None,
            "catalysts": [],
            "key_risks": [],
        },
        "scores": {
            "potential_score": None,
            "fundamentals_score": None,
            "technicals_score": None,
            "momentum_score": None,
            "score_label": None,
            "importance_ranked_items": [],
            "confidence_score": None,
        },
        "sources": [
            {
                "name": "stub",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


def generate_card(ticker: str, progress_callback=None) -> Dict[str, Any]:
    card = empty_card(ticker)
    _cb = progress_callback or (lambda msg: None)

    _cb("Récupération des données en cours...")

    def _fetch_identity():
        cached = _cache.load(ticker, "identity")
        if cached:
            return cached
        data = fetch_identity_and_market(ticker)
        _cache.save(ticker, "identity", data)
        return data

    def _fetch_momentum():
        cached = _cache.load(ticker, "momentum")
        if cached:
            return cached
        data = compute_momentum_12m(ticker)
        if data:
            _cache.save(ticker, "momentum", data)
        return data

    def _has_useful_fundamentals(payload):
        if not payload:
            return False
        fin = payload.get("financials", {})
        val = payload.get("valuation", {})
        return sum(1 for v in {**fin, **val}.values() if v is not None) >= 3

    def _fetch_fundamentals():
        cached = _cache.load(ticker, "fundamentals")
        if _has_useful_fundamentals(cached):
            return cached
        data = fetch_core_fundamentals(ticker)
        if _has_useful_fundamentals(data):
            _cache.save(ticker, "fundamentals", data)
        return data

    def _fetch_technicals():
        cached = _cache.load(ticker, "technicals")
        if cached:
            return cached
        data = compute_technicals(ticker)
        _cache.save(ticker, "technicals", data)
        return data

    with ThreadPoolExecutor() as executor:
        future_id = executor.submit(_fetch_identity)
        future_mom = executor.submit(_fetch_momentum)
        future_fund = executor.submit(_fetch_fundamentals)
        future_tech = executor.submit(_fetch_technicals)

        # identity + market
        try:
            data = future_id.result()
            card["identity"].update(
                {k: v for k, v in data["identity"].items() if v is not None}
            )
            card["market"].update(
                {k: v for k, v in data["market"].items() if v is not None}
            )
            card["sources"].append(
                {
                    "name": data.get("source", "yfinance"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _cb("✓ Identité & données de marché")
        except Exception as e:
            logger.error(f"Error fetching identity/market for {ticker}: {e}")
            _cb("⚠ Identité & données de marché (erreur)")

        # momentum
        try:
            mom = future_mom.result()
            if mom is not None:
                card["market"].update({k: v for k, v in mom.items() if v is not None})
            _cb("✓ Momentum calculé")
        except Exception as e:
            logger.error(f"Error computing momentum for {ticker}: {e}")
            _cb("⚠ Momentum (erreur)")

        # fundamentals
        try:
            f = future_fund.result()
            card["financials"].update(
                {k: v for k, v in f["financials"].items() if v is not None}
            )
            card["valuation"].update(
                {k: v for k, v in f["valuation"].items() if v is not None}
            )
            _cb("✓ Fondamentaux récupérés")
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker}: {e}")
            _cb("⚠ Fondamentaux (erreur)")

        # technicals
        try:
            tech = future_tech.result()
            card["technicals"].update(
                {k: v for k, v in tech.items() if v is not None}
            )
            _cb("✓ Indicateurs techniques")
        except Exception as e:
            logger.error(f"Error computing technicals for {ticker}: {e}")
            _cb("⚠ Indicateurs techniques (erreur)")

    # Momentum relatif au secteur (post-executor : requiert le secteur de l'identity)
    _cb("Momentum relatif au secteur...")
    try:
        sector = card["identity"].get("sector")
        rel_mom = compute_relative_momentum(ticker, sector)
        if rel_mom:
            card["market"].update({k: v for k, v in rel_mom.items() if v is not None})
    except Exception as e:
        logger.error(f"Error computing relative momentum for {ticker}: {e}")

    # LLM enrichment (business snapshot + events)
    _cb("Analyse IA en cours...")
    try:
        cached_llm = _cache.load(ticker, "llm")
        if cached_llm:
            llm_data = cached_llm
            _cb("✓ Analyse IA (cache)")
        else:
            llm_data = enrich_with_llm(card)
            if llm_data:
                _cache.save(ticker, "llm", llm_data)
        if llm_data:
            card["business_snapshot"].update(
                {k: v for k, v in llm_data.get("business_snapshot", {}).items() if v is not None}
            )
            card["events"].update(
                {k: v for k, v in llm_data.get("events", {}).items() if v is not None}
            )
            _cb("✓ Analyse IA terminée")
        else:
            _cb("— Analyse IA (clé non configurée)")
    except Exception as e:
        logger.error(f"LLM enrichment failed for {ticker}: {e}")
        _cb("⚠ Analyse IA (erreur)")

    # scoring
    _cb("Calcul du score de potentiel...")
    breakdown = compute_potential_score(card)
    _cb("Analyse des facteurs clés...")
    card["scores"]["importance_ranked_items"] = build_importance_items(card, limit=10)

    _cb("Score de confiance...")
    confidence = compute_confidence_score(card)
    card["scores"]["confidence_score"] = confidence

    # Ajustement par la confiance — appliqué à chaque sous-score pour que
    # la décomposition reste cohérente avec le total affiché.
    #
    # FIX I1 (audit 2026-05-13) : Le multiplicateur historique `0.5 + 0.5*conf/100`
    # provoquait une double pénalisation lorsque les fondamentaux étaient
    # absents : `score_linear` retourne déjà 50 (neutre) sur None, et le facteur
    # x0.5 transformait ce 50 neutre en un score affiché de ~25 ("Faible").
    # On relève le plancher de 0.5 → 0.8 pour limiter la sur-pénalisation tout
    # en gardant le signal "données peu fiables → score modulé légèrement".
    factor = 0.8 + 0.2 * (confidence or 0) / 100
    card["scores"]["potential_score"]    = int(round(breakdown["total"]        * factor))
    card["scores"]["fundamentals_score"] = int(round(breakdown["fundamentals"] * factor))
    card["scores"]["technicals_score"]   = int(round(breakdown["technicals"]   * factor))
    card["scores"]["momentum_score"]     = int(round(breakdown["momentum"]     * factor))

    # FIX I4 (audit 2026-05-13) : appliquer le label sur le score brut (avant
    # factor) plutôt que sur le score affiché. Garantit qu'une entreprise de
    # fondamentaux solides reste étiquetée "Fort" même quand la confidence est
    # basse (données partielles), sans gonfler artificiellement le score.
    card["scores"]["score_label"] = _score_label(int(round(breakdown["total"])))
    _cb("Analyse terminée !")

    # Aucune écriture ici : generate_card calcule, il ne persiste pas.
    # L'appel à core.supabase_sink.upsert_ticker_score() qui vivait à cet
    # endroit lisait SUPABASE_SERVICE_ROLE_KEY, une variable qui n'a jamais
    # été définie sur le VPS — il était donc no-op depuis toujours, et le
    # retirer ne fait perdre aucune écriture. La persistance est faite par
    # l'appelant (daemon ou CLI) via core.storage.writer.write_score().
    return card


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", help="e.g. AAPL")
    parser.add_argument("--outdir", default="data/cards", help="output directory")
    args = parser.parse_args()

    card = generate_card(args.ticker)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f"{args.ticker.upper()}.json"

    outpath.write_text(
        json.dumps(card, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {outpath}")


if __name__ == "__main__":
    main()
