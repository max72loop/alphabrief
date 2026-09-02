"""Sélection + trades avec cap turnover par priorité |Δscore|."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from core.paper_portfolio.corporate_actions import Position


Action = Literal["BUY", "SELL", "SHORT", "COVER"]
PortfolioName = Literal["TOP10", "BOTTOM10", "LONG_SHORT", "SPY_BENCHMARK"]
DropReason = Literal["TURNOVER_CAP", "INSUFFICIENT_CASH", "PRICE_MISSING"]


@dataclass(frozen=True)
class ScoredTicker:
    ticker: str
    score: int
    sector: str
    price_friday_close: float


@dataclass(frozen=True)
class Trade:
    ticker: str
    action: Action
    shares: float
    price: float
    fees: float
    slippage: float
    score_at_decision: Optional[int]
    rationale: str
    delta_score: int


@dataclass(frozen=True)
class DroppedTrade:
    trade: Trade
    reason: DropReason


@dataclass(frozen=True)
class RebalancePlan:
    portfolio_id: int
    portfolio_name: PortfolioName
    rebalance_date: date
    trades: list[Trade]
    dropped_trades: list[DroppedTrade]
    turnover_pct: float
    cash_before: float
    cash_after: float
    total_fees: float
    total_slippage: float


def select_top10(scores: list[ScoredTicker]) -> list[ScoredTicker]:
    """Top 10 par score desc, bornés par la bande haute du barème.

    Les bornes 80/30 ont été retirées de config.py (seuils morts : le moteur
    plafonne à 68). Une reprise de ce module doit lire core.scoring.bands.
    """
    raise NotImplementedError


def select_bottom10(scores: list[ScoredTicker]) -> list[ScoredTicker]:
    """Bottom 10 par score asc, bornés par la bande basse du barème.

    Voir select_top10 : bornes à reprendre de core.scoring.bands.
    """
    raise NotImplementedError


def compute_rebalance(
    portfolio_name: PortfolioName,
    portfolio_id: int,
    current_positions: list[Position],
    current_cash: float,
    target_tickers: list[ScoredTicker],
    monday_open_prices: dict[str, float],
    previous_scores: dict[str, int],
    rebalance_date: date,
) -> RebalancePlan:
    """Calcule trades, trie par |Δscore| desc, cappe à TURNOVER_CAP du NAV.

    Raises InsufficientCashError si cash résiduel < 0 même après élagage.
    """
    raise NotImplementedError


def compute_genesis(
    portfolio_name: PortfolioName,
    portfolio_id: int,
    initial_capital: float,
    target_tickers: list[ScoredTicker],
    monday_open_prices: dict[str, float],
    rebalance_date: date,
) -> RebalancePlan:
    """Premier rebalance : émet ligne GENESIS + BUY/SHORT initiaux."""
    raise NotImplementedError


def dollar_neutral_long_short(
    top_tickers: list[ScoredTicker],
    bottom_tickers: list[ScoredTicker],
    total_capital: float,
    monday_open_prices: dict[str, float],
) -> tuple[list[Trade], list[Trade]]:
    """Jambes 50/50. Invariant : |Σ long - Σ short| / capital ≤ 0.005."""
    raise NotImplementedError
