"""Hiérarchie d'exceptions spécifiques au module Paper Portfolio."""
from __future__ import annotations


class PaperPortfolioError(Exception):
    """Racine de la hiérarchie, catch-all côté job pour logging structuré."""


class ChainBrokenError(PaperPortfolioError):
    """Incohérence détectée dans la hash-chain rebalances."""

    def __init__(self, message: str, broken_at_index: int) -> None:
        super().__init__(message)
        self.broken_at_index = broken_at_index


class InsufficientCashError(PaperPortfolioError):
    """Cash résiduel négatif même après élagage des trades."""


class InvalidScoreError(PaperPortfolioError):
    """Score hors [0,100] ou breakdown invalide."""


class UniverseEmptyError(PaperPortfolioError):
    """Univers de sélection insuffisant (ex. < 10 tickers ≥ seuil TOP)."""


class CorporateActionError(PaperPortfolioError):
    """Erreur lors de l'application d'un événement corporate action."""
