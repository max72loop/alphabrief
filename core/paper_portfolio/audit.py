"""Export JSON canonique pour /api/proof/audit."""
from __future__ import annotations

from typing import TypedDict


class AuditBundle(TypedDict):
    generated_at: str
    portfolio: dict
    rebalances: list[dict]
    nav_history: list[dict]
    corporate_actions: list[dict]
    missed_rebalances: list[dict]
    chain_verification: dict


def build_audit_bundle(
    portfolio_row: dict,
    rebalances: list[dict],
    nav_history: list[dict],
    corporate_actions: list[dict],
    missed_rebalances: list[dict],
) -> AuditBundle:
    """Agrège + vérifie hash-chain. Raises ChainBrokenError si cassée."""
    raise NotImplementedError


def canonical_json_bytes(bundle: AuditBundle) -> bytes:
    """JSON canonique (sorted_keys, separators=(',',':'))."""
    raise NotImplementedError


def audit_root_hash(bundle: AuditBundle) -> str:
    """SHA256 hex du bundle canonique. Preuve racine à publier."""
    raise NotImplementedError
