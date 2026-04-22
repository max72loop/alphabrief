"""Constantes du module Paper Portfolio — lit /root/.env (fallback defaults).

Aucune fonction publique — juste des constantes au top-level. Les helpers
privés _get_float_env / _get_int_env sont réels (pas de stub) parce qu'ils
sont utilisés à l'import par les autres constantes.
"""
from __future__ import annotations

import os
from typing import Final, Literal


def _get_float_env(key: str, default: float) -> float:
    raw = os.environ.get(key)
    return float(raw) if raw is not None else default


def _get_int_env(key: str, default: int) -> int:
    raw = os.environ.get(key)
    return int(raw) if raw is not None else default


# ── Capital & coûts ────────────────────────────────────────────────────
INITIAL_CAPITAL: Final[float] = _get_float_env("PAPER_PORTFOLIO_INITIAL_CAPITAL", 100_000.0)
FEES_BPS: Final[int] = _get_int_env("PAPER_PORTFOLIO_FEES_BPS", 10)
SLIPPAGE_BPS: Final[int] = _get_int_env("PAPER_PORTFOLIO_SLIPPAGE_BPS", 5)
BORROW_COST_BPS_ANNUAL: Final[int] = _get_int_env("PAPER_PORTFOLIO_BORROW_COST_BPS_ANNUAL", 50)
TURNOVER_CAP: Final[float] = _get_float_env("PAPER_PORTFOLIO_TURNOVER_CAP", 0.15)

# ── Timing ──────────────────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR: Final[int] = 252
REBALANCE_TIMEZONE: Final[str] = "America/New_York"
REBALANCE_DAY: Final[Literal["MONDAY"]] = "MONDAY"
REBALANCE_HOUR_ET: Final[int] = 9
REBALANCE_MINUTE_ET: Final[int] = 30

# ── Sélection ──────────────────────────────────────────────────────────
SCORE_THRESHOLD_TOP: Final[int] = 80
SCORE_THRESHOLD_BOTTOM: Final[int] = 30
TOP_COUNT: Final[int] = 10
BOTTOM_COUNT: Final[int] = 10
BENCHMARK_TICKER: Final[str] = "SPY"

# ── Univers ────────────────────────────────────────────────────────────
UNIVERSE: Final[Literal["SP500"]] = "SP500"

# ── Portfolios ─────────────────────────────────────────────────────────
PORTFOLIO_NAMES: Final[tuple[str, ...]] = ("TOP10", "BOTTOM10", "LONG_SHORT", "SPY_BENCHMARK")

# ── Gating métriques (côté UI, exposé ici pour référence) ──────────────
METRICS_SAMPLE_DAYS_MIN: Final[int] = 30
METRICS_SAMPLE_DAYS_FULL: Final[int] = 90

# ── Risk-free source ───────────────────────────────────────────────────
RISK_FREE_RATE_SOURCE: Final[Literal["SOFR"]] = "SOFR"
