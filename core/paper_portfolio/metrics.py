"""Métriques de performance annualisées (252j)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PerformanceMetrics:
    sharpe: Optional[float]
    sortino: Optional[float]
    max_drawdown: float
    win_rate: float
    alpha_vs_spy: Optional[float]
    beta: Optional[float]
    sample_days: int


def compute_metrics(
    portfolio_returns: list[float],
    spy_returns: Optional[list[float]] = None,
    risk_free_rate_annual: float = 0.0,
) -> PerformanceMetrics:
    """Calcule tout. sharpe/sortino=None si sample_days < 2."""
    raise NotImplementedError


def sharpe_ratio(returns: list[float], risk_free_rate_annual: float = 0.0) -> Optional[float]:
    """Sharpe annualisé. None si std==0 ou len < 2."""
    raise NotImplementedError


def sortino_ratio(returns: list[float], risk_free_rate_annual: float = 0.0) -> Optional[float]:
    """Sortino annualisé. None si downside_std==0 ou len < 2."""
    raise NotImplementedError


def max_drawdown(nav_series: list[float]) -> float:
    """Max DD observé, ≤ 0. 0 si série monotone croissante."""
    raise NotImplementedError


def win_rate(returns: list[float]) -> float:
    """Ratio de jours avec return > 0."""
    raise NotImplementedError


def alpha_beta_ols(
    portfolio_returns: list[float],
    spy_returns: list[float],
) -> tuple[Optional[float], Optional[float]]:
    """Régression OLS ; alpha × 252 pour annualisation. (None, None) si len < 20."""
    raise NotImplementedError
