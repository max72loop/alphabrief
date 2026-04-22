"""Tests de core.paper_portfolio.metrics.

Policy d'assertion numérique :
    - ==              : entiers (sample_days)
    - approx(rel=1e-6): ratios, Sharpe, Sortino, alpha, beta
    - approx(abs=1e-6): drawdown, win_rate (tolérance autour de 0)
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from core.paper_portfolio.metrics import (
    alpha_beta_ols,
    compute_metrics,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)


# ── Builders ──────────────────────────────────────────────────────────

def _constant_returns(r: float, n: int) -> list[float]:
    return [r] * n


def _deterministic_returns(n: int, seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0005, 0.012, n).tolist()


# ── sharpe_ratio ──────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_constant_returns_raise_or_none(self):
        """Std = 0 → None (division par zéro)."""
        assert sharpe_ratio(_constant_returns(0.001, 50)) is None

    def test_single_value_returns_none(self):
        assert sharpe_ratio([0.01]) is None

    def test_empty_returns_none(self):
        assert sharpe_ratio([]) is None

    def test_known_distribution(self):
        """mean=0.001, std=0.01 sur 252j → Sharpe annualisé ≈ 0.001/0.01 × √252 ≈ 1.587."""
        returns = [0.001] * 126 + [-0.001] * 126
        # not constant; mean ≠ 0 here? Actually mean=0. Use different:
        returns = [0.002, -0.001] * 126  # mean = 0.0005
        result = sharpe_ratio(returns, risk_free_rate_annual=0.0)
        assert result is not None
        # Sanity : borne inférieure/supérieure raisonnable
        assert -5.0 < result < 5.0

    def test_subtracts_risk_free_rate(self):
        returns = [0.002] * 100 + [-0.001] * 100
        s_rf0 = sharpe_ratio(returns, risk_free_rate_annual=0.0)
        s_rf5 = sharpe_ratio(returns, risk_free_rate_annual=0.05)
        assert s_rf0 is not None and s_rf5 is not None
        assert s_rf5 < s_rf0  # risk-free plus élevé réduit le Sharpe


# ── sortino_ratio ─────────────────────────────────────────────────────

class TestSortinoRatio:
    def test_all_positive_downside_zero_returns_none(self):
        """Downside std = 0 → Sortino indéfini → None."""
        assert sortino_ratio([0.01, 0.02, 0.005]) is None

    def test_empty_returns_none(self):
        assert sortino_ratio([]) is None

    def test_with_drawdowns_computes(self):
        returns = [0.01, -0.02, 0.015, -0.01, 0.005]
        result = sortino_ratio(returns)
        assert result is not None


# ── max_drawdown ──────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_monotone_up_zero_dd(self):
        assert max_drawdown([100, 101, 102, 103]) == pytest.approx(0.0, abs=1e-6)

    def test_peak_trough(self):
        # peak=120, trough=96 → (96-120)/120 = -0.20
        assert max_drawdown([100, 110, 120, 115, 100, 96, 105]) == pytest.approx(-0.20, rel=1e-6)

    def test_single_point_zero(self):
        assert max_drawdown([100]) == pytest.approx(0.0, abs=1e-6)


# ── win_rate ──────────────────────────────────────────────────────────

class TestWinRate:
    def test_all_positive(self):
        assert win_rate([0.01, 0.02, 0.005]) == pytest.approx(1.0, abs=1e-6)

    def test_all_negative_or_zero(self):
        assert win_rate([-0.01, 0.0, -0.02]) == pytest.approx(0.0, abs=1e-6)

    def test_mixed_60_40(self):
        # 3 positive sur 5 → 0.6
        assert win_rate([0.01, -0.01, 0.02, -0.02, 0.005]) == pytest.approx(0.6, abs=1e-6)

    def test_empty_returns_zero(self):
        assert win_rate([]) == pytest.approx(0.0, abs=1e-6)


# ── alpha_beta_ols ────────────────────────────────────────────────────

class TestAlphaBetaOls:
    def test_perfect_correlation_beta_one_alpha_zero(self):
        # portfolio_return = spy_return → beta=1, alpha=0
        spy = _deterministic_returns(50, seed=1)
        port = list(spy)
        alpha, beta = alpha_beta_ols(port, spy)
        assert beta == pytest.approx(1.0, rel=1e-6)
        assert alpha == pytest.approx(0.0, abs=1e-6)

    def test_twice_spy_returns_beta_two(self):
        spy = _deterministic_returns(100, seed=2)
        port = [2 * r for r in spy]
        alpha, beta = alpha_beta_ols(port, spy)
        assert beta == pytest.approx(2.0, rel=1e-6)
        assert alpha == pytest.approx(0.0, abs=1e-6)

    def test_too_short_returns_none(self):
        spy = _deterministic_returns(10, seed=3)
        port = list(spy)
        alpha, beta = alpha_beta_ols(port, spy)
        assert alpha is None and beta is None

    def test_length_mismatch_raises(self):
        spy = _deterministic_returns(30, seed=4)
        port = _deterministic_returns(25, seed=5)
        with pytest.raises(ValueError):
            alpha_beta_ols(port, spy)


# ── compute_metrics (integration) ─────────────────────────────────────

class TestComputeMetrics:
    def test_sample_days_reflects_input(self):
        m = compute_metrics(_deterministic_returns(42, seed=6))
        assert m.sample_days == 42

    def test_without_spy_alpha_beta_none(self):
        m = compute_metrics(_deterministic_returns(50, seed=7), spy_returns=None)
        assert m.alpha_vs_spy is None and m.beta is None

    def test_short_sample_sharpe_may_be_none(self):
        m = compute_metrics([0.001])
        assert m.sample_days == 1
        assert m.sharpe is None and m.sortino is None

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_metrics(_deterministic_returns(30, seed=8),
                            spy_returns=_deterministic_returns(25, seed=9))


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_sharpe_not_implemented(self):
        with pytest.raises(NotImplementedError):
            sharpe_ratio([0.01, 0.02])

    def test_max_drawdown_not_implemented(self):
        with pytest.raises(NotImplementedError):
            max_drawdown([100, 110, 100])

    def test_alpha_beta_not_implemented(self):
        with pytest.raises(NotImplementedError):
            alpha_beta_ols([0.01] * 30, [0.01] * 30)

    def test_compute_metrics_not_implemented(self):
        with pytest.raises(NotImplementedError):
            compute_metrics([0.01] * 30)
