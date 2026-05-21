"""
Récupère l'identité et les données de marché d'un ticker via FMP (stable API).
Remplace l'ancienne version basée sur yfinance.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.providers.fmp_client import fmp_get

logger = logging.getLogger(__name__)


def _normalize_dividend_yield(raw_yield: Optional[float]) -> Optional[float]:
    """Normalise le dividend yield en format décimal (0.0041 = 0.41%).

    WARNING: double-divide risk if upstream already in pct. La fonction
    tente de détecter le format par heuristique mais ce n'est pas fiable
    à 100%. Si val > 100, on considère que c'est bogué et on retourne 0.0.
    """
    if raw_yield is None:
        return None
    val = float(raw_yield)
    # Guard : valeur > 100% impossible en pratique → données corrompues.
    if val > 100.0:
        return 0.0  # bogus
    if val > 1.0:
        return val / 100.0
    elif val > 0.20:
        return val / 100.0
    return val


def _fetch_analyst_targets(ticker: str) -> dict:
    """Fetch analyst price targets / recommendations.

    Source primaire: FMP stable API (price-target-consensus, ratings-snapshot).
    Fallback: yfinance Ticker.info en cas d'échec FMP (utile pour les tickers
    internationaux non couverts par le plan FMP Starter).
    """
    result = {
        "analyst_target_mean": None,
        "analyst_target_low": None,
        "analyst_target_high": None,
        "analyst_count": None,
        "analyst_recommendation": None,
    }

    # 1) Try FMP price-target-consensus
    try:
        consensus = fmp_get("price-target-consensus", {"symbol": ticker})
        if isinstance(consensus, list) and consensus:
            c = consensus[0]
            result["analyst_target_mean"] = c.get("targetConsensus") or c.get("targetMedian")
            result["analyst_target_low"] = c.get("targetLow")
            result["analyst_target_high"] = c.get("targetHigh")
    except Exception as e:
        logger.debug(f"FMP price-target-consensus failed for {ticker}: {e}")

    # 2) Try FMP ratings-snapshot for recommendation
    try:
        ratings = fmp_get("ratings-snapshot", {"symbol": ticker})
        if isinstance(ratings, list) and ratings:
            r = ratings[0]
            result["analyst_recommendation"] = r.get("rating") or r.get("ratingRecommendation")
    except Exception as e:
        logger.debug(f"FMP ratings-snapshot failed for {ticker}: {e}")

    # 3) Fallback yfinance si FMP n'a rien donné
    if result["analyst_target_mean"] is None and result["analyst_recommendation"] is None:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            if result["analyst_target_mean"] is None:
                result["analyst_target_mean"] = info.get("targetMeanPrice")
            if result["analyst_target_low"] is None:
                result["analyst_target_low"] = info.get("targetLowPrice")
            if result["analyst_target_high"] is None:
                result["analyst_target_high"] = info.get("targetHighPrice")
            if result["analyst_count"] is None:
                result["analyst_count"] = info.get("numberOfAnalystOpinions")
            if result["analyst_recommendation"] is None:
                result["analyst_recommendation"] = info.get("recommendationKey")
        except Exception as e:
            logger.debug(f"yfinance analyst fallback failed for {ticker}: {e}")

    return result


def _parse_range(range_str: str):
    """Parse FMP range string '123.45-678.90' into (low, high)."""
    if not range_str or "-" not in range_str:
        return None, None
    parts = range_str.split("-")
    try:
        return float(parts[0].strip()), float(parts[-1].strip())
    except (ValueError, IndexError):
        return None, None


def fetch_identity_and_market(ticker: str) -> dict:
    profile_list = fmp_get("profile", {"symbol": ticker})
    quote_list = fmp_get("quote", {"symbol": ticker})

    profile = profile_list[0] if profile_list and len(profile_list) > 0 else {}
    quote = quote_list[0] if quote_list and len(quote_list) > 0 else {}

    # Current price and daily change
    current_price = quote.get("price") or profile.get("price")
    prev_close = quote.get("previousClose")
    change_pct = quote.get("changePercentage")
    if change_pct is None and current_price and prev_close and prev_close > 0:
        change_pct = ((current_price - prev_close) / prev_close) * 100

    # 52-week range
    fifty_two_low = quote.get("yearLow")
    fifty_two_high = quote.get("yearHigh")
    if fifty_two_low is None or fifty_two_high is None:
        low, high = _parse_range(profile.get("range", ""))
        fifty_two_low = fifty_two_low or low
        fifty_two_high = fifty_two_high or high

    # Dividend yield
    div_yield = None
    last_div = profile.get("lastDividend")
    if last_div and current_price and current_price > 0:
        div_yield = _normalize_dividend_yield(last_div / current_price)

    # Business description - truncate if too long
    description = profile.get("description") or ""
    if len(description) > 300:
        description = description[:297] + "..."

    # Analyst consensus (FMP + yfinance fallback)
    analysts = _fetch_analyst_targets(ticker)

    return {
        "identity": {
            "name": profile.get("companyName"),
            "exchange": profile.get("exchange") or profile.get("exchangeFullName"),
            "currency": profile.get("currency"),
            "market_cap": profile.get("marketCap") or quote.get("marketCap"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "description": description,
            "website": profile.get("website"),
            "employees": profile.get("fullTimeEmployees"),
        },
        "market": {
            "beta": profile.get("beta"),
            "avg_volume_3m": profile.get("averageVolume"),
            "current_price": current_price,
            "previous_close": prev_close,
            "change_pct": change_pct,
            "volume": profile.get("volume") or quote.get("volume"),
            "fifty_two_week_low": fifty_two_low,
            "fifty_two_week_high": fifty_two_high,
            "dividend_yield": div_yield,
            # Analyst consensus (FMP price-target-consensus + ratings-snapshot,
            # yfinance fallback pour les tickers internationaux)
            "analyst_target_mean": analysts["analyst_target_mean"],
            "analyst_target_low": analysts["analyst_target_low"],
            "analyst_target_high": analysts["analyst_target_high"],
            "analyst_count": analysts["analyst_count"],
            "analyst_recommendation": analysts["analyst_recommendation"],
        },
        "source": "fmp",
    }
