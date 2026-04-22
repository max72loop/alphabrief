"""Hash-chain SHA256 chaînée pour paper_rebalances (preuve immuable)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict

GENESIS_PREV_HASH: str = "0" * 64


class RebalanceRow(TypedDict):
    """Champs canoniques inclus dans le hash (exclut id, created_at, *_hash).

    shares / price / fees / slippage sont des strings pour déterminisme
    (Decimal sérialisé avec 4 décimales fixes).
    """
    portfolio_id: int
    rebalance_date: str
    action: str
    ticker: str
    shares: str
    price: str
    fees: str
    slippage: str
    score_at_decision: Optional[int]
    rationale: Optional[str]


@dataclass(frozen=True)
class HashedRebalance:
    row: RebalanceRow
    prev_hash: str
    row_hash: str


def canonical_serialize(row: RebalanceRow) -> bytes:
    """JSON canonique, clés triées, pas d'espaces. Raises ValueError si invalide."""
    raise NotImplementedError


def compute_row_hash(row: RebalanceRow, prev_hash: str) -> str:
    """SHA256 hex de (prev_hash bytes || canonical_serialize(row))."""
    raise NotImplementedError


def chain_rebalances(
    rows: list[RebalanceRow],
    initial_prev_hash: str = GENESIS_PREV_HASH,
) -> list[HashedRebalance]:
    """Chaîne une séquence en produisant prev_hash + row_hash pour chaque ligne."""
    raise NotImplementedError


def verify_chain(hashed_rows: list[HashedRebalance]) -> None:
    """Vérifie l'intégrité. Raises ChainBrokenError avec broken_at_index."""
    raise NotImplementedError
