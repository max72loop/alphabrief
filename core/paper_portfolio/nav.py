"""Calcul de NAV quotidien : mark-to-market + cash SOFR + borrow EOD.

Contrat prix manquants (important) :
    1. Prix null sur ticker actif → utiliser last_known_price + warning log
    2. 3 jours null consécutifs → SUSPENSION_AUTO_DETECTED, événement créé,
       freeze de la position au dernier prix connu
    3. JAMAIS assumer 0
    4. JAMAIS skip silencieusement la position

Contrat cash BOD (Begin Of Day) :
    cash_balance dans NAVInput est le solde AVANT intérêt/borrow du jour.
    Exemple : cash_bod=8000$, sofr=4.32% annuel
              cash_interest = 8000 × 0.0432 / 252 = 1.37$
              cash_eod     = 8000 + 1.37 - borrow_cost
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, TypedDict

from core.paper_portfolio.corporate_actions import Position


@dataclass(frozen=True)
class PriceSnapshot:
    ticker: str
    close: float


@dataclass(frozen=True)
class NAVComponents:
    date: date
    long_value: float
    short_value: float
    short_pnl: float
    cash_balance: float
    cash_interest: float
    borrow_cost: float
    nav: float


class NAVInput(TypedDict):
    portfolio_id: int
    positions: list[Position]
    cash_balance: float
    prices: dict[str, float]
    last_known_prices: dict[str, float]
    consecutive_null_days: dict[str, int]
    sofr_rate_annual: float
    date_: date


def compute_nav(inp: NAVInput) -> NAVComponents:
    """Calcule la NAV quotidienne. Invariant :
    nav == long_value + short_pnl + (cash_balance + cash_interest - borrow_cost).
    """
    raise NotImplementedError


def daily_cash_interest(cash_balance: float, sofr_annual: float) -> float:
    """cash × sofr_annual / TRADING_DAYS_PER_YEAR. Raises ValueError si cash < 0."""
    raise NotImplementedError


def daily_borrow_cost(eod_short_notional: float) -> float:
    """notional × (BORROW_COST_BPS_ANNUAL/10000) / TRADING_DAYS_PER_YEAR.
    Note : utilise le notional POST mark-to-market, pas entry notional.
    """
    raise NotImplementedError


def drawdown_from_history(nav_series: list[float]) -> float:
    """(NAV_courant - peak_depuis_debut) / peak. Retourne ≤ 0."""
    raise NotImplementedError


def cumulative_return(current_nav: float, initial_nav: float) -> float:
    """(current / initial) - 1."""
    raise NotImplementedError


def daily_return(today_nav: float, yesterday_nav: float) -> float:
    """(today / yesterday) - 1."""
    raise NotImplementedError


def resolve_price(
    ticker: str,
    today_price: Optional[float],
    last_known_price: Optional[float],
    consecutive_null_days_so_far: int,
) -> tuple[float, Optional[str], int]:
    """Applique le contrat prix manquants.

    Returns (resolved_price, warning_or_None, new_consecutive_null_count).
    Raises CorporateActionError si 3e jour null consécutif (trigger SUSPENSION_AUTO_DETECTED).
    """
    raise NotImplementedError
