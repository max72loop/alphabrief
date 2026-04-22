"""Tests de core.paper_portfolio.nav.

Policy d'assertion numérique :
    - ==              : entiers (shares int, portfolio_id, sample_days)
    - approx(abs=0.01): montants cash USD (précision au cent)
    - approx(rel=1e-6): ratios, returns, NAV décimaux

Jamais d'== sur floats calculés.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.paper_portfolio.corporate_actions import Position
from core.paper_portfolio.exceptions import CorporateActionError
from core.paper_portfolio.nav import (
    NAVInput,
    compute_nav,
    cumulative_return,
    daily_borrow_cost,
    daily_cash_interest,
    daily_return,
    drawdown_from_history,
    resolve_price,
)


# ── Builders ──────────────────────────────────────────────────────────

def _long(ticker: str, shares: float, entry_price: float) -> Position:
    return Position(ticker=ticker, side="LONG", shares=shares,
                    entry_price=entry_price, entry_date=date(2026, 4, 13))


def _short(ticker: str, shares: float, entry_price: float) -> Position:
    return Position(ticker=ticker, side="SHORT", shares=shares,
                    entry_price=entry_price, entry_date=date(2026, 4, 13))


def _nav_input(
    positions: list[Position],
    cash_balance: float,
    prices: dict[str, float],
    sofr_rate_annual: float = 0.0432,
) -> NAVInput:
    return NAVInput(
        portfolio_id=1,
        positions=positions,
        cash_balance=cash_balance,
        prices=prices,
        last_known_prices=dict(prices),
        consecutive_null_days={},
        sofr_rate_annual=sofr_rate_annual,
        date_=date(2026, 4, 20),
    )


# ── compute_nav ───────────────────────────────────────────────────────

class TestComputeNav:
    def test_long_only_happy_path(self):
        positions = [_long("AAPL", 100, 150.0), _long("MSFT", 50, 300.0)]
        inp = _nav_input(positions, cash_balance=5000.0,
                         prices={"AAPL": 155.0, "MSFT": 310.0})
        nav = compute_nav(inp)
        # long_value = 100*155 + 50*310 = 30500
        assert nav.long_value == pytest.approx(30500.0, abs=0.01)
        assert nav.short_value == pytest.approx(0.0, abs=0.01)
        assert nav.borrow_cost == pytest.approx(0.0, abs=0.01)
        # invariant
        expected = (nav.long_value + nav.short_pnl
                    + nav.cash_balance + nav.cash_interest - nav.borrow_cost)
        assert nav.nav == pytest.approx(expected, abs=0.01)

    def test_mixed_long_short(self):
        positions = [_long("AAPL", 100, 150.0), _short("XYZ", 50, 80.0)]
        inp = _nav_input(positions, cash_balance=10000.0,
                         prices={"AAPL": 155.0, "XYZ": 75.0})
        nav = compute_nav(inp)
        # short_pnl = (80 - 75) × 50 = 250
        assert nav.short_pnl == pytest.approx(250.0, abs=0.01)
        # short_value = 50*75 = 3750 → borrow on this
        assert nav.short_value == pytest.approx(3750.0, abs=0.01)
        assert nav.borrow_cost > 0

    def test_invariant_nav_formula(self):
        positions = [_long("AAPL", 100, 150.0), _short("XYZ", 50, 80.0)]
        inp = _nav_input(positions, cash_balance=10000.0,
                         prices={"AAPL": 155.0, "XYZ": 75.0})
        nav = compute_nav(inp)
        recomputed = (nav.long_value + nav.short_pnl + nav.cash_balance
                      + nav.cash_interest - nav.borrow_cost)
        assert nav.nav == pytest.approx(recomputed, abs=0.01)

    def test_missing_price_raises_keyerror(self):
        positions = [_long("AAPL", 100, 150.0)]
        inp = _nav_input(positions, cash_balance=1000.0, prices={})
        with pytest.raises(KeyError):
            compute_nav(inp)


# ── daily_cash_interest ───────────────────────────────────────────────

class TestDailyCashInterest:
    def test_simple_positive(self):
        # 8000 × 0.0432 / 252 ≈ 1.3714
        got = daily_cash_interest(8000.0, 0.0432)
        assert got == pytest.approx(8000.0 * 0.0432 / 252, rel=1e-6)

    def test_zero_cash_zero_interest(self):
        assert daily_cash_interest(0.0, 0.05) == pytest.approx(0.0, abs=0.01)

    def test_zero_rate_zero_interest(self):
        assert daily_cash_interest(10000.0, 0.0) == pytest.approx(0.0, abs=0.01)

    def test_negative_cash_raises(self):
        with pytest.raises(ValueError):
            daily_cash_interest(-1.0, 0.05)


# ── daily_borrow_cost ─────────────────────────────────────────────────

class TestDailyBorrowCost:
    def test_positive_notional(self):
        # BORROW=50 bps annuel, notional 10000 → 10000*0.005/252 ≈ 0.1984
        got = daily_borrow_cost(10000.0)
        assert got == pytest.approx(10000.0 * 0.005 / 252, rel=1e-6)

    def test_zero_notional_zero_cost(self):
        assert daily_borrow_cost(0.0) == pytest.approx(0.0, abs=0.01)


# ── drawdown_from_history ────────────────────────────────────────────

class TestDrawdownFromHistory:
    def test_monotone_up_no_drawdown(self):
        assert drawdown_from_history([100, 101, 102, 103]) == pytest.approx(0.0, abs=1e-6)

    def test_single_point(self):
        assert drawdown_from_history([100]) == pytest.approx(0.0, abs=1e-6)

    def test_known_drawdown(self):
        # peak=120, current=108 → (108-120)/120 = -0.10
        assert drawdown_from_history([100, 120, 115, 108]) == pytest.approx(-0.10, rel=1e-6)


# ── cumulative_return ─────────────────────────────────────────────────

def test_cumulative_return_simple():
    assert cumulative_return(105.0, 100.0) == pytest.approx(0.05, rel=1e-6)


def test_cumulative_return_flat():
    assert cumulative_return(100.0, 100.0) == pytest.approx(0.0, abs=1e-6)


# ── daily_return ──────────────────────────────────────────────────────

def test_daily_return_positive():
    assert daily_return(102.0, 100.0) == pytest.approx(0.02, rel=1e-6)


def test_daily_return_negative():
    assert daily_return(99.0, 100.0) == pytest.approx(-0.01, rel=1e-6)


# ── resolve_price (contrat prix manquants) ────────────────────────────

class TestResolvePrice:
    def test_today_price_present(self):
        px, warn, count = resolve_price("AAPL", 155.0, 150.0, 0)
        assert px == pytest.approx(155.0, abs=0.01)
        assert warn is None
        assert count == 0

    def test_null_falls_back_to_last_known(self):
        px, warn, count = resolve_price("AAPL", None, 150.0, 0)
        assert px == pytest.approx(150.0, abs=0.01)
        assert warn is not None
        assert count == 1

    def test_second_null_increments_counter(self):
        px, warn, count = resolve_price("AAPL", None, 150.0, 1)
        assert px == pytest.approx(150.0, abs=0.01)
        assert count == 2

    def test_third_null_triggers_suspension(self):
        with pytest.raises(CorporateActionError, match="SUSPENSION_AUTO_DETECTED"):
            resolve_price("AAPL", None, 150.0, 2)

    def test_never_assumes_zero(self):
        """Si last_known_price est None ET today None → erreur, pas 0."""
        with pytest.raises((ValueError, CorporateActionError)):
            resolve_price("AAPL", None, None, 0)


# ── Fixtures cross-check : SOFR values are plausible ─────────────────

def test_mock_sofr_rates_in_plausible_range(mock_sofr):
    for entry in mock_sofr["rates"]:
        assert 0.03 <= entry["rate"] <= 0.06  # fixture window 4.30-4.60%


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_compute_nav_not_implemented(self):
        positions = [_long("AAPL", 100, 150.0)]
        inp = _nav_input(positions, 1000.0, {"AAPL": 155.0})
        with pytest.raises(NotImplementedError):
            compute_nav(inp)

    def test_daily_cash_interest_not_implemented(self):
        with pytest.raises(NotImplementedError):
            daily_cash_interest(1000.0, 0.04)

    def test_daily_borrow_cost_not_implemented(self):
        with pytest.raises(NotImplementedError):
            daily_borrow_cost(5000.0)

    def test_resolve_price_not_implemented(self):
        with pytest.raises(NotImplementedError):
            resolve_price("AAPL", 150.0, None, 0)
