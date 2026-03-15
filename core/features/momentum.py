from __future__ import annotations

from typing import Dict, Optional

import yfinance as yf


# Mapping secteur → ETF SPDR correspondant (S&P 500 sector ETFs)
# Utilisé pour le calcul du momentum relatif au secteur.
# Fallback sur SPY (S&P 500) si secteur inconnu.
_SECTOR_ETFS: Dict[str, str] = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Financial Services":     "XLF",  # Yahoo Finance utilise ce label pour banques/fintech
    "Health Care":            "XLV",
    "Energy":                 "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Materials":              "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
}
_DEFAULT_BENCHMARK = "SPY"


def compute_relative_momentum(ticker: str, sector: Optional[str]) -> Dict[str, Optional[float]]:
    """
    Calcule la performance du titre RELATIVE à l'ETF de son secteur.

    relative_momentum = stock_return − sector_ETF_return

    Exemples :
    - Titre +20% / Secteur +25% → relative = −5%  (sous-performance)
    - Titre +10% / Secteur −5%  → relative = +15% (forte surperformance)

    Utilise yf.download() multi-ticker pour un seul appel réseau.
    Retourne un dict vide si les données sont insuffisantes.
    """
    benchmark = _SECTOR_ETFS.get(sector or "", _DEFAULT_BENCHMARK)
    try:
        data = yf.download(
            [ticker, benchmark],
            period="1y",
            auto_adjust=True,
            progress=False,
        )
        if data.empty:
            return {}

        # yf.download multi-ticker → MultiIndex columns (metric, ticker)
        close = data["Close"]
        if ticker not in close.columns or benchmark not in close.columns:
            return {}

        stock_c = close[ticker].dropna()
        bench_c = close[benchmark].dropna()

        # Aligner sur les dates communes (jours de cotisation partagés)
        common = stock_c.index.intersection(bench_c.index)
        if len(common) < 21:
            return {}

        stock_c = stock_c.loc[common]
        bench_c = bench_c.loc[common]
        n = len(common)
        last_s = float(stock_c.iloc[-1])
        last_b = float(bench_c.iloc[-1])

        def _rel(bars: int) -> Optional[float]:
            if n < bars:
                return None
            s_ret = 100.0 * (last_s / float(stock_c.iloc[-bars]) - 1.0)
            b_ret = 100.0 * (last_b / float(bench_c.iloc[-bars]) - 1.0)
            return round(s_ret - b_ret, 2)

        return {
            "relative_momentum_12m": _rel(min(252, n)),
            "relative_momentum_3m":  _rel(63),
            "relative_momentum_1m":  _rel(21),
        }
    except Exception:
        return {}


def compute_momentum_12m(ticker: str) -> Dict[str, Optional[float]] | None:
    """
    Calcule la performance sur plusieurs horizons à partir d'un seul fetch 1Y.

    Retourne un dict avec :
      - momentum_1m  : performance sur ~21 séances (≈ 1 mois)
      - momentum_3m  : performance sur ~63 séances (≈ 3 mois)
      - momentum_6m  : performance sur ~126 séances (≈ 6 mois)
      - momentum_12m : performance sur toute la période fetchée (≈ 12 mois)

    Retourne None si les données sont insuffisantes.
    """
    hist = yf.Ticker(ticker).history(period="1y")
    if hist is None or hist.empty:
        return None

    # Supprimer les barres NaN : yfinance peut retourner une première barre incomplète
    # ce qui rend iloc[0] et iloc[-252] NaN et fausse tous les calculs de retour.
    close = hist["Close"].dropna()
    n = len(close)
    if n < 21:  # Pas assez de données même pour le 1m
        return None

    last = float(close.iloc[-1])

    def _ret(n_bars: int) -> Optional[float]:
        """Retour (%) sur les n_bars dernières séances."""
        if n < n_bars:
            return None
        first = float(close.iloc[-n_bars])
        if not (first > 0):
            return None
        return 100.0 * (last / first - 1.0)

    return {
        "momentum_1m":  _ret(21),
        "momentum_3m":  _ret(63),
        "momentum_6m":  _ret(126),
        # Utilise _ret(min(252, n)) plutôt que iloc[0] : yfinance peut retourner
        # NaN sur la première barre d'une période "1y" (barre initiale incomplète),
        # ce qui rendait mom_12m=None même avec 12 mois de données disponibles.
        "momentum_12m": _ret(min(252, n)),
    }
