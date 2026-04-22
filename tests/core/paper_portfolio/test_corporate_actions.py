"""Tests de core.paper_portfolio.corporate_actions sur fixtures réelles.

Couvre les 7 types d'événements (SPLIT, REVERSE_SPLIT, DIVIDEND, SPINOFF,
MERGER_CASH, MERGER_STOCK, DELISTING, SUSPENSION) + cas ADR ex_date=null.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.paper_portfolio.corporate_actions import (
    CorporateEvent,
    Position,
    apply_delisting,
    apply_dividend,
    apply_event,
    apply_merger,
    apply_spinoff,
    apply_split,
    apply_suspension,
    resolve_effective_date,
)
from core.paper_portfolio.exceptions import CorporateActionError


# ── Builders ──────────────────────────────────────────────────────────

def _long(ticker: str = "AAPL", shares: float = 100.0, entry_price: float = 150.0) -> Position:
    return Position(
        ticker=ticker, side="LONG", shares=shares,
        entry_price=entry_price, entry_date=date(2026, 1, 5),
    )


def _short(ticker: str = "XYZT", shares: float = 50.0, entry_price: float = 80.0) -> Position:
    return Position(
        ticker=ticker, side="SHORT", shares=shares,
        entry_price=entry_price, entry_date=date(2026, 1, 5),
    )


def _event_from_fixture(fixture: dict, index: int = 0) -> CorporateEvent:
    ev = fixture["events"][index]
    return CorporateEvent(
        ticker=ev["ticker"],
        action_type=ev["action_type"],
        effective_date=date.fromisoformat(ev["effective_date"]),
        details=ev["details"],
    )


# ── apply_split ───────────────────────────────────────────────────────

class TestApplySplit:
    def test_long_2_for_1_doubles_shares_halves_entry(self, mock_splits):
        event = _event_from_fixture(mock_splits)
        pos = _long(ticker="NVDA", shares=100.0, entry_price=400.0)
        result = apply_split(pos, event)
        assert result.new_position is not None
        assert result.new_position.shares == 200.0
        assert result.new_position.entry_price == 200.0
        assert result.cash_delta == 0.0

    def test_short_split_preserves_notional(self, mock_splits):
        event = _event_from_fixture(mock_splits)
        pos = _short(ticker="NVDA", shares=50.0, entry_price=400.0)
        result = apply_split(pos, event)
        assert result.new_position.shares == 100.0
        assert result.new_position.entry_price == 200.0
        assert result.cash_delta == 0.0

    def test_invalid_ratio_raises(self):
        pos = _long("NVDA")
        bad = CorporateEvent(
            ticker="NVDA", action_type="SPLIT",
            effective_date=date(2026, 5, 15),
            details={"ratio_new": 0, "ratio_old": 1},
        )
        with pytest.raises(ValueError):
            apply_split(pos, bad)


# ── apply_dividend ────────────────────────────────────────────────────

class TestApplyDividend:
    def test_long_receives_cash(self, mock_dividends):
        event = _event_from_fixture(mock_dividends, index=0)  # KO normal
        pos = _long(ticker="KO", shares=200.0, entry_price=60.0)
        result = apply_dividend(pos, event)
        assert result.cash_delta == pytest.approx(200.0 * 0.48, rel=1e-6)
        assert result.new_position == pos  # shares/entry_price inchangés
        assert result.warning is None

    def test_short_pays_dividend_to_lender(self, mock_dividends):
        event = _event_from_fixture(mock_dividends, index=0)
        pos = _short(ticker="KO", shares=200.0, entry_price=60.0)
        result = apply_dividend(pos, event)
        assert result.cash_delta == pytest.approx(-200.0 * 0.48, rel=1e-6)

    def test_adr_null_ex_date_emits_warning(self, mock_dividends):
        """Cas critique : ex_date null → fallback payment_date - 1bd + warning."""
        event = _event_from_fixture(mock_dividends, index=1)  # BABA ADR
        pos = _long(ticker="BABA", shares=10.0, entry_price=120.0)
        result = apply_dividend(pos, event)
        assert result.warning == "EX_DATE_MISSING"
        assert result.log_entry.get("fallback_rule") == "payment_date - 1 business day"

    def test_zero_amount_no_cash_delta(self):
        pos = _long("KO")
        event = CorporateEvent(
            ticker="KO", action_type="DIVIDEND",
            effective_date=date(2026, 5, 15),
            details={"amount": 0.0, "currency": "USD", "ex_date": "2026-05-15",
                     "payment_date": "2026-06-02"},
        )
        result = apply_dividend(pos, event)
        assert result.cash_delta == 0.0


# ── apply_delisting ───────────────────────────────────────────────────

class TestApplyDelisting:
    def test_long_liquidated_at_last_price(self, mock_delistings):
        event = _event_from_fixture(mock_delistings)
        pos = _long(ticker="XYZT", shares=100.0, entry_price=50.0)
        result = apply_delisting(pos, event)
        assert result.new_position is None
        assert result.cash_delta == pytest.approx(100.0 * 45.20, rel=1e-6)

    def test_short_cover_pnl_correct(self, mock_delistings):
        """SHORT covered at last_price : P&L = (entry - last_price) × shares."""
        event = _event_from_fixture(mock_delistings)
        pos = _short(ticker="XYZT", shares=100.0, entry_price=50.0)
        result = apply_delisting(pos, event)
        assert result.new_position is None
        # cover: on "rachète" à 45.20, on a vendu à 50 → gain 4.80/share
        expected = (50.0 - 45.20) * 100.0
        assert result.cash_delta == pytest.approx(expected, rel=1e-6)

    def test_missing_last_price_uses_zero(self):
        pos = _long("XXX")
        event = CorporateEvent(
            ticker="XXX", action_type="DELISTING",
            effective_date=date(2026, 5, 1), details={"reason": "UNKNOWN"},
        )
        result = apply_delisting(pos, event)
        assert result.cash_delta == 0.0


# ── apply_spinoff ─────────────────────────────────────────────────────

class TestApplySpinoff:
    def test_spinoff_liquidates_and_logs_policy(self):
        pos = _long("PARENT", shares=50.0, entry_price=100.0)
        event = CorporateEvent(
            ticker="PARENT", action_type="SPINOFF",
            effective_date=date(2026, 5, 15),
            details={"spinoff_ticker": "CHILD", "last_close_before": 99.50},
        )
        result = apply_spinoff(pos, event)
        assert result.new_position is None
        assert result.log_entry.get("corporate_action_type") == "SPINOFF"
        assert "LIQUIDATION" in result.log_entry.get("action", "").upper()


# ── apply_merger ──────────────────────────────────────────────────────

class TestApplyMerger:
    def test_merger_cash_closes_at_announced(self):
        pos = _long("TGT", shares=100.0, entry_price=80.0)
        event = CorporateEvent(
            ticker="TGT", action_type="MERGER_CASH",
            effective_date=date(2026, 6, 1),
            details={"announced_price": 95.00},
        )
        result = apply_merger(pos, event)
        assert result.new_position is None
        assert result.cash_delta == pytest.approx(9500.0, rel=1e-6)

    def test_merger_stock_not_in_universe_liquidates(self):
        pos = _long("TGT", shares=100.0, entry_price=80.0)
        event = CorporateEvent(
            ticker="TGT", action_type="MERGER_STOCK",
            effective_date=date(2026, 6, 1),
            details={"new_ticker": "FOREIGN_XYZ", "ratio": 1.2, "last_close_before": 90.0},
        )
        result = apply_merger(pos, event)
        assert result.new_position is None  # liquidation par défaut


# ── apply_suspension ──────────────────────────────────────────────────

class TestApplySuspension:
    def test_suspension_start_position_unchanged(self):
        pos = _long("HALT", shares=100.0, entry_price=50.0)
        event = CorporateEvent(
            ticker="HALT", action_type="SUSPENSION",
            effective_date=date(2026, 5, 10),
            details={"phase": "SUSPENSION_START"},
        )
        result = apply_suspension(pos, event)
        assert result.new_position == pos
        assert result.cash_delta == 0.0
        assert "SUSPENSION" in result.log_entry.get("phase", "")


# ── apply_event (dispatcher) ──────────────────────────────────────────

class TestApplyEventDispatcher:
    def test_routes_to_correct_handler(self, mock_splits):
        event = _event_from_fixture(mock_splits)
        pos = _long(ticker="NVDA", shares=50.0, entry_price=400.0)
        result_direct = apply_split(pos, event)
        result_via_dispatch = apply_event(pos, event)
        assert result_via_dispatch.new_position == result_direct.new_position


# ── resolve_effective_date ────────────────────────────────────────────

class TestResolveEffectiveDate:
    def test_ex_date_present_returned_as_is(self, mock_dividends):
        event = _event_from_fixture(mock_dividends, index=0)
        d, warning = resolve_effective_date(event)
        assert d == date(2026, 5, 15)
        assert warning is None

    def test_ex_date_null_falls_back_to_payment_minus_one_bd(self, mock_dividends):
        event = _event_from_fixture(mock_dividends, index=1)
        d, warning = resolve_effective_date(event)
        assert d == date(2026, 5, 22)  # payment 2026-05-25 lundi → vendredi 22
        assert warning == "EX_DATE_MISSING"


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_apply_split_not_implemented(self, mock_splits):
        with pytest.raises(NotImplementedError):
            apply_split(_long(), _event_from_fixture(mock_splits))

    def test_apply_dividend_not_implemented(self, mock_dividends):
        with pytest.raises(NotImplementedError):
            apply_dividend(_long("KO"), _event_from_fixture(mock_dividends))

    def test_apply_delisting_not_implemented(self, mock_delistings):
        with pytest.raises(NotImplementedError):
            apply_delisting(_long("XYZT"), _event_from_fixture(mock_delistings))

    def test_resolve_effective_date_not_implemented(self, mock_dividends):
        with pytest.raises(NotImplementedError):
            resolve_effective_date(_event_from_fixture(mock_dividends))
