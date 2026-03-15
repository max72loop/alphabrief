import yfinance as yf


def _normalize_dividend_yield(raw_yield):
    """
    Normalise le dividend yield en format décimal (0.0041 = 0.41%).
    yfinance peut retourner le yield en format incohérent selon les versions.
    """
    if raw_yield is None:
        return None
    val = float(raw_yield)
    if val > 1.0:
        # Valeur > 100% impossible, probablement en pourcentage (ex: 41 = 41%)
        return val / 100.0
    elif val > 0.20:
        # Valeur > 20% très improbable, probablement format % direct (ex: 0.41 = 0.41%)
        # Normaliser en décimal : 0.41 → 0.0041
        return val / 100.0
    return val


def fetch_identity_and_market(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info or {}

    # Current price and daily change
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose")
    change_pct = None
    if current_price and prev_close and prev_close > 0:
        change_pct = ((current_price - prev_close) / prev_close) * 100

    # 52-week range
    fifty_two_week_low = info.get("fiftyTwoWeekLow")
    fifty_two_week_high = info.get("fiftyTwoWeekHigh")

    # Business description - truncate if too long
    description = info.get("longBusinessSummary") or ""
    if len(description) > 300:
        description = description[:297] + "..."

    return {
        "identity": {
            "name": info.get("shortName"),
            "exchange": info.get("exchange"),
            "currency": info.get("currency"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "description": description,
            "website": info.get("website"),
            "employees": info.get("fullTimeEmployees"),
        },
        "market": {
            "beta": info.get("beta"),
            "avg_volume_3m": info.get("averageVolume"),
            "current_price": current_price,
            "previous_close": prev_close,
            "change_pct": change_pct,
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "fifty_two_week_low": fifty_two_week_low,
            "fifty_two_week_high": fifty_two_week_high,
            "dividend_yield": _normalize_dividend_yield(info.get("dividendYield")),
            # Analyst consensus
            "analyst_target_mean": info.get("targetMeanPrice"),
            "analyst_target_low": info.get("targetLowPrice"),
            "analyst_target_high": info.get("targetHighPrice"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "analyst_recommendation": info.get("recommendationKey"),
        },
        "source": "yfinance"
    }
