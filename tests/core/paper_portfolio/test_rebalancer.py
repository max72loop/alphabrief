"""Tests de core.paper_portfolio.rebalancer sur fixtures réelles (500 scores).

Policy d'assertion numérique :
    - ==              : entiers (shares int si équipondération exacte, delta_score)
    - approx(abs=0.01): montants cash USD, notionals, fees
    - approx(rel=1e-6): ratios (turnover_pct, deltas normalisés)
"""
from __future__ import annotations

from datetime import date

import pytest

from core.paper_portfolio.corporate_actions import Position
from core.paper_portfolio.exceptions import InsufficientCashError, UniverseEmptyError
from core.paper_portfolio.rebalancer import (
    ScoredTicker,
    compute_genesis,
    compute_rebalance,
    dollar_neutral_long_short,
    select_bottom10,
    select_top10,
)


# ── Builders ──────────────────────────────────────────────────────────

def _scored_from_fixture(mock_sp500_scores: dict) -> list[ScoredTicker]:
    return [
        ScoredTicker(
            ticker=s["ticker"],
            score=s["score"],
            sector=s["sector"],
            price_friday_close=s["price_friday_close"],
        )
        for s in mock_sp500_scores["scores"]
    ]


def _monday_prices_from_fixture(mock_prices_week: dict) -> dict[str, float]:
    return {
        tkr: data["next_monday_open"]["price"]
        for tkr, data in mock_prices_week["tickers"].items()
    }


def _long(ticker: str, shares: float, entry_price: float) -> Position:
    return Position(ticker=ticker, side="LONG", shares=shares,
                    entry_price=entry_price, entry_date=date(2026, 4, 13))


# ── select_top10 ──────────────────────────────────────────────────────

class TestSelectTop10:
    def test_happy_path_returns_10_desc(self, mock_sp500_scores):
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        assert len(top) == 10
        assert top[0].score >= top[-1].score
        assert all(t.score >= 80 for t in top)

    def test_raises_universe_empty_if_less_than_10_above_threshold(self):
        low_universe = [ScoredTicker(f"T{i}", 50, "Tech", 100.0) for i in range(20)]
        with pytest.raises(UniverseEmptyError):
            select_top10(low_universe)


# ── select_bottom10 ───────────────────────────────────────────────────

class TestSelectBottom10:
    def test_happy_path_returns_10_asc(self, mock_sp500_scores):
        scored = _scored_from_fixture(mock_sp500_scores)
        bot = select_bottom10(scored)
        assert len(bot) == 10
        assert bot[0].score <= bot[-1].score
        assert all(t.score <= 30 for t in bot)

    def test_raises_universe_empty_if_less_than_10_below_threshold(self):
        high_universe = [ScoredTicker(f"T{i}", 70, "Tech", 100.0) for i in range(20)]
        with pytest.raises(UniverseEmptyError):
            select_bottom10(high_universe)


# ── compute_rebalance ─────────────────────────────────────────────────

class TestComputeRebalance:
    def test_happy_path_top10_genesis_like(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        plan = compute_rebalance(
            portfolio_name="TOP10", portfolio_id=1,
            current_positions=[], current_cash=100_000.0,
            target_tickers=top, monday_open_prices=monday,
            previous_scores={},  # premier rebalance
            rebalance_date=date(2026, 4, 20),
        )
        assert plan.portfolio_name == "TOP10"
        assert plan.cash_after >= 0
        # tous les trades sont BUY (nouvelles positions long)
        assert all(t.action == "BUY" for t in plan.trades)

    def test_turnover_cap_caps_trades(self, mock_sp500_scores, mock_prices_week):
        """Si changement de tout le TOP10 d'un coup, turnover_pct ≤ TURNOVER_CAP."""
        from core.paper_portfolio.config import TURNOVER_CAP
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        # positions existantes = 10 tickers différents du top
        alien_positions = [_long(f"ALIEN{i}", 100.0, 50.0) for i in range(10)]
        monday_full = {**monday, **{f"ALIEN{i}": 50.0 for i in range(10)}}
        plan = compute_rebalance(
            portfolio_name="TOP10", portfolio_id=1,
            current_positions=alien_positions,
            current_cash=5000.0,
            target_tickers=top, monday_open_prices=monday_full,
            previous_scores={f"ALIEN{i}": 0 for i in range(10)},
            rebalance_date=date(2026, 4, 20),
        )
        assert plan.turnover_pct <= TURNOVER_CAP + 1e-6

    def test_dropped_trades_logged(self, mock_sp500_scores, mock_prices_week):
        """Trades évincés par le cap turnover apparaissent dans dropped_trades."""
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        alien_positions = [_long(f"ALIEN{i}", 100.0, 50.0) for i in range(10)]
        monday_full = {**monday, **{f"ALIEN{i}": 50.0 for i in range(10)}}
        plan = compute_rebalance(
            portfolio_name="TOP10", portfolio_id=1,
            current_positions=alien_positions,
            current_cash=5000.0,
            target_tickers=top, monday_open_prices=monday_full,
            previous_scores={f"ALIEN{i}": 0 for i in range(10)},
            rebalance_date=date(2026, 4, 20),
        )
        # avec 10 aliens à remplacer par 10 top, il y a des trades à couper sous cap 15%
        assert len(plan.dropped_trades) > 0

    def test_priority_delta_score_descending(self, mock_sp500_scores, mock_prices_week):
        """Les trades sont ordonnés par |Δscore| décroissant."""
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        plan = compute_rebalance(
            portfolio_name="TOP10", portfolio_id=1,
            current_positions=[], current_cash=100_000.0,
            target_tickers=top, monday_open_prices=monday,
            previous_scores={},
            rebalance_date=date(2026, 4, 20),
        )
        deltas = [t.delta_score for t in plan.trades]
        assert deltas == sorted(deltas, reverse=True)

    def test_insufficient_cash_raises(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        with pytest.raises(InsufficientCashError):
            compute_rebalance(
                portfolio_name="TOP10", portfolio_id=1,
                current_positions=[], current_cash=1.0,  # 1$ de cash, impossible
                target_tickers=top, monday_open_prices=monday,
                previous_scores={},
                rebalance_date=date(2026, 4, 20),
            )


# ── compute_genesis ───────────────────────────────────────────────────

class TestComputeGenesis:
    def test_emits_genesis_line(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        plan = compute_genesis(
            portfolio_name="TOP10", portfolio_id=1,
            initial_capital=100_000.0,
            target_tickers=top, monday_open_prices=monday,
            rebalance_date=date(2026, 4, 20),
        )
        # Première ligne : GENESIS sentinelle
        actions = [t.action for t in plan.trades]
        assert actions[0] == "GENESIS" or any(
            getattr(t, "action", None) == "GENESIS" for t in plan.trades
        )


# ── dollar_neutral_long_short ────────────────────────────────────────

class TestDollarNeutralLongShort:
    def test_dollar_neutral_within_half_percent(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        top = select_top10(scored)
        bot = select_bottom10(scored)
        monday = _monday_prices_from_fixture(mock_prices_week)
        longs, shorts = dollar_neutral_long_short(
            top_tickers=top, bottom_tickers=bot,
            total_capital=100_000.0, monday_open_prices=monday,
        )
        long_notional = sum(t.shares * t.price for t in longs)
        short_notional = sum(t.shares * t.price for t in shorts)
        diff = abs(long_notional - short_notional) / 100_000.0
        assert diff <= 0.005  # invariant 50 bps


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_select_top10_not_implemented(self, mock_sp500_scores):
        with pytest.raises(NotImplementedError):
            select_top10(_scored_from_fixture(mock_sp500_scores))

    def test_select_bottom10_not_implemented(self, mock_sp500_scores):
        with pytest.raises(NotImplementedError):
            select_bottom10(_scored_from_fixture(mock_sp500_scores))

    def test_compute_rebalance_not_implemented(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        with pytest.raises(NotImplementedError):
            compute_rebalance(
                portfolio_name="TOP10", portfolio_id=1,
                current_positions=[], current_cash=100_000.0,
                target_tickers=scored[:10],
                monday_open_prices=_monday_prices_from_fixture(mock_prices_week),
                previous_scores={},
                rebalance_date=date(2026, 4, 20),
            )

    def test_compute_genesis_not_implemented(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        with pytest.raises(NotImplementedError):
            compute_genesis(
                portfolio_name="TOP10", portfolio_id=1,
                initial_capital=100_000.0,
                target_tickers=scored[:10],
                monday_open_prices=_monday_prices_from_fixture(mock_prices_week),
                rebalance_date=date(2026, 4, 20),
            )

    def test_dollar_neutral_not_implemented(self, mock_sp500_scores, mock_prices_week):
        scored = _scored_from_fixture(mock_sp500_scores)
        with pytest.raises(NotImplementedError):
            dollar_neutral_long_short(
                top_tickers=scored[:10], bottom_tickers=scored[-10:],
                total_capital=100_000.0,
                monday_open_prices=_monday_prices_from_fixture(mock_prices_week),
            )
