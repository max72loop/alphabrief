"""Tests de core.paper_portfolio.config — constantes + env overrides."""
from __future__ import annotations

import importlib

import pytest

from core.paper_portfolio import config as cfg


class TestDefaults:
    def test_initial_capital_default_100k(self):
        assert cfg.INITIAL_CAPITAL == 100_000.0

    def test_fees_bps_default_10(self):
        assert cfg.FEES_BPS == 10

    def test_slippage_bps_default_5(self):
        assert cfg.SLIPPAGE_BPS == 5

    def test_borrow_cost_default_50(self):
        assert cfg.BORROW_COST_BPS_ANNUAL == 50

    def test_turnover_cap_default_15pct(self):
        assert cfg.TURNOVER_CAP == 0.15

    def test_trading_days_252(self):
        assert cfg.TRADING_DAYS_PER_YEAR == 252

    def test_portfolio_names_exactly_four(self):
        assert cfg.PORTFOLIO_NAMES == ("TOP10", "BOTTOM10", "LONG_SHORT", "SPY_BENCHMARK")

    def test_score_thresholds_are_gone(self):
        """Les seuils 80/30 ont été retirés le 2026-09-02 (seuils morts).

        Ce test garde la porte fermée : les rouvrir ici signifierait redéclarer
        un barème à côté de core.scoring.bands, ce que la refonte a supprimé.
        """
        assert not hasattr(cfg, "SCORE_THRESHOLD_TOP")
        assert not hasattr(cfg, "SCORE_THRESHOLD_BOTTOM")

    def test_metrics_gating_thresholds_ordered(self):
        assert cfg.METRICS_SAMPLE_DAYS_MIN == 30
        assert cfg.METRICS_SAMPLE_DAYS_FULL == 90
        assert cfg.METRICS_SAMPLE_DAYS_MIN < cfg.METRICS_SAMPLE_DAYS_FULL

    def test_benchmark_is_spy(self):
        assert cfg.BENCHMARK_TICKER == "SPY"

    def test_rebalance_time_is_us_open(self):
        assert cfg.REBALANCE_TIMEZONE == "America/New_York"
        assert cfg.REBALANCE_HOUR_ET == 9
        assert cfg.REBALANCE_MINUTE_ET == 30


class TestTypes:
    def test_numeric_types(self):
        assert isinstance(cfg.INITIAL_CAPITAL, float)
        assert isinstance(cfg.FEES_BPS, int)
        assert isinstance(cfg.SLIPPAGE_BPS, int)
        assert isinstance(cfg.BORROW_COST_BPS_ANNUAL, int)
        assert isinstance(cfg.TURNOVER_CAP, float)

    def test_portfolio_names_is_tuple(self):
        assert isinstance(cfg.PORTFOLIO_NAMES, tuple)
        assert all(isinstance(n, str) for n in cfg.PORTFOLIO_NAMES)


class TestEnvOverride:
    """Vérifie qu'un env override est pris en compte au rechargement du module."""

    def test_fees_bps_override(self, monkeypatch):
        monkeypatch.setenv("PAPER_PORTFOLIO_FEES_BPS", "25")
        reloaded = importlib.reload(cfg)
        try:
            assert reloaded.FEES_BPS == 25
        finally:
            monkeypatch.delenv("PAPER_PORTFOLIO_FEES_BPS", raising=False)
            importlib.reload(cfg)

    def test_turnover_cap_override(self, monkeypatch):
        monkeypatch.setenv("PAPER_PORTFOLIO_TURNOVER_CAP", "0.25")
        reloaded = importlib.reload(cfg)
        try:
            assert reloaded.TURNOVER_CAP == 0.25
        finally:
            monkeypatch.delenv("PAPER_PORTFOLIO_TURNOVER_CAP", raising=False)
            importlib.reload(cfg)

    def test_invalid_int_raises_on_reload(self, monkeypatch):
        monkeypatch.setenv("PAPER_PORTFOLIO_FEES_BPS", "not-a-number")
        with pytest.raises(ValueError):
            importlib.reload(cfg)
        monkeypatch.delenv("PAPER_PORTFOLIO_FEES_BPS", raising=False)
        importlib.reload(cfg)


# Note : pas de TestNotYetImplementedSentinel — config.py n'a pas de stubs,
# que des constantes. La valeur est testée directement ci-dessus.
