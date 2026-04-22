"""Tests de core.paper_portfolio.audit — export JSON public + vérif chain."""
from __future__ import annotations

import hashlib
import json

import pytest

from core.paper_portfolio.audit import (
    audit_root_hash,
    build_audit_bundle,
    canonical_json_bytes,
)
from core.paper_portfolio.exceptions import ChainBrokenError
from core.paper_portfolio.hash_chain import (
    GENESIS_PREV_HASH,
    chain_rebalances,
)


# ── Builders ──────────────────────────────────────────────────────────

def _portfolio_row() -> dict:
    return {
        "id": 1, "name": "TOP10", "strategy": "Top 10 by score",
        "initial_capital": 100_000.0, "started_at": "2026-04-20",
    }


def _rebalance_row_dict(ticker: str, action: str = "BUY",
                        prev_hash: str = GENESIS_PREV_HASH,
                        row_hash: str | None = None) -> dict:
    base = {
        "portfolio_id": 1,
        "rebalance_date": "2026-04-20",
        "action": action,
        "ticker": ticker,
        "shares": "10.0000",
        "price": "100.00",
        "fees": "1.0000",
        "slippage": "0.5000",
        "score_at_decision": 85,
        "rationale": "test",
        "prev_hash": prev_hash,
        "row_hash": row_hash or ("a" * 64),
    }
    return base


def _valid_rebalances() -> list[dict]:
    """Construit 3 rebalances avec hash-chain valide en passant par chain_rebalances."""
    from core.paper_portfolio.hash_chain import RebalanceRow

    rows: list[RebalanceRow] = [
        {
            "portfolio_id": 1, "rebalance_date": "2026-04-20", "action": "GENESIS",
            "ticker": "_GENESIS_", "shares": "0.0000", "price": "0.00",
            "fees": "0.00", "slippage": "0.00",
            "score_at_decision": None, "rationale": "genesis",
        },
        {
            "portfolio_id": 1, "rebalance_date": "2026-04-20", "action": "BUY",
            "ticker": "AAPL", "shares": "52.6315", "price": "190.00",
            "fees": "10.00", "slippage": "5.00",
            "score_at_decision": 85, "rationale": "top10",
        },
    ]
    chained = chain_rebalances(rows)
    return [
        {**dict(c.row), "prev_hash": c.prev_hash, "row_hash": c.row_hash}
        for c in chained
    ]


# ── build_audit_bundle ────────────────────────────────────────────────

class TestBuildAuditBundle:
    def test_happy_path_aggregates_sections(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[{"date": "2026-04-20", "nav": 100_000.0}],
            corporate_actions=[],
            missed_rebalances=[],
        )
        assert bundle["portfolio"]["name"] == "TOP10"
        assert len(bundle["rebalances"]) == 2
        assert len(bundle["nav_history"]) == 1
        assert "generated_at" in bundle

    def test_chain_verification_passes_on_valid(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        assert bundle["chain_verification"]["verified"] is True

    def test_chain_broken_raises(self):
        rebalances = _valid_rebalances()
        rebalances[1]["row_hash"] = "f" * 64  # tamper
        with pytest.raises(ChainBrokenError):
            build_audit_bundle(
                portfolio_row=_portfolio_row(),
                rebalances=rebalances,
                nav_history=[], corporate_actions=[], missed_rebalances=[],
            )


# ── canonical_json_bytes ──────────────────────────────────────────────

class TestCanonicalJsonBytes:
    def test_deterministic_same_input_same_bytes(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        assert canonical_json_bytes(bundle) == canonical_json_bytes(bundle)

    def test_no_whitespace(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        out = canonical_json_bytes(bundle)
        assert b" " not in out
        assert b"\n" not in out

    def test_parses_back_to_equivalent_dict(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        out = canonical_json_bytes(bundle)
        reparsed = json.loads(out.decode())
        assert reparsed["portfolio"]["name"] == "TOP10"


# ── audit_root_hash ───────────────────────────────────────────────────

class TestAuditRootHash:
    def test_returns_64_hex(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        h = audit_root_hash(bundle)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_matches_manual_sha256_of_canonical(self):
        bundle = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        expected = hashlib.sha256(canonical_json_bytes(bundle)).hexdigest()
        assert audit_root_hash(bundle) == expected

    def test_different_content_different_hash(self):
        b1 = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[], corporate_actions=[], missed_rebalances=[],
        )
        b2 = build_audit_bundle(
            portfolio_row=_portfolio_row(),
            rebalances=_valid_rebalances(),
            nav_history=[{"date": "2026-04-20", "nav": 100_001.0}],
            corporate_actions=[], missed_rebalances=[],
        )
        assert audit_root_hash(b1) != audit_root_hash(b2)


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_build_audit_bundle_not_implemented(self):
        with pytest.raises(NotImplementedError):
            build_audit_bundle(
                portfolio_row=_portfolio_row(), rebalances=[],
                nav_history=[], corporate_actions=[], missed_rebalances=[],
            )

    def test_canonical_json_bytes_not_implemented(self):
        bundle = {
            "generated_at": "", "portfolio": {}, "rebalances": [],
            "nav_history": [], "corporate_actions": [], "missed_rebalances": [],
            "chain_verification": {},
        }
        with pytest.raises(NotImplementedError):
            canonical_json_bytes(bundle)  # type: ignore[arg-type]

    def test_audit_root_hash_not_implemented(self):
        bundle = {
            "generated_at": "", "portfolio": {}, "rebalances": [],
            "nav_history": [], "corporate_actions": [], "missed_rebalances": [],
            "chain_verification": {},
        }
        with pytest.raises(NotImplementedError):
            audit_root_hash(bundle)  # type: ignore[arg-type]
