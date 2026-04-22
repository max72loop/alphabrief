"""Tests unitaires pour core.paper_portfolio.hash_chain.

Stratégie : la hash-chain étant le pilier de la preuve anti-triche, chaque
invariant documenté dans les docstrings du module est couvert par au moins
un test explicite. Module stdlib-only, pas de fixtures JSON.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from core.paper_portfolio.exceptions import ChainBrokenError
from core.paper_portfolio.hash_chain import (
    GENESIS_PREV_HASH,
    HashedRebalance,
    RebalanceRow,
    canonical_serialize,
    chain_rebalances,
    compute_row_hash,
    verify_chain,
)


# ── Builders ──────────────────────────────────────────────────────────

def _make_row(
    portfolio_id: int = 1,
    rebalance_date: str = "2026-04-20",
    action: str = "BUY",
    ticker: str = "AAPL",
    shares: str = "52.6315",
    price: str = "190.00",
    fees: str = "10.00",
    slippage: str = "5.00",
    score_at_decision: int | None = 85,
    rationale: str | None = "score ≥ 80 threshold",
) -> RebalanceRow:
    return RebalanceRow(
        portfolio_id=portfolio_id,
        rebalance_date=rebalance_date,
        action=action,
        ticker=ticker,
        shares=shares,
        price=price,
        fees=fees,
        slippage=slippage,
        score_at_decision=score_at_decision,
        rationale=rationale,
    )


def _genesis_row(portfolio_id: int = 1) -> RebalanceRow:
    return _make_row(
        portfolio_id=portfolio_id,
        action="GENESIS",
        ticker="_GENESIS_",
        shares="0.0000",
        price="0.00",
        fees="0.00",
        slippage="0.00",
        score_at_decision=None,
        rationale="portfolio genesis",
    )


# ── canonical_serialize ───────────────────────────────────────────────

class TestCanonicalSerialize:
    def test_happy_path_returns_bytes(self):
        out = canonical_serialize(_make_row())
        assert isinstance(out, bytes)
        assert json.loads(out.decode()) == dict(_make_row())

    def test_deterministic_across_key_order(self):
        row_a: RebalanceRow = {
            "portfolio_id": 1, "rebalance_date": "2026-04-20", "action": "BUY",
            "ticker": "AAPL", "shares": "10.0000", "price": "190.00",
            "fees": "1.0000", "slippage": "0.5000",
            "score_at_decision": 85, "rationale": "x",
        }
        row_b: RebalanceRow = {
            "rationale": "x", "score_at_decision": 85, "slippage": "0.5000",
            "fees": "1.0000", "price": "190.00", "shares": "10.0000",
            "ticker": "AAPL", "action": "BUY", "rebalance_date": "2026-04-20",
            "portfolio_id": 1,
        }
        assert canonical_serialize(row_a) == canonical_serialize(row_b)

    def test_no_whitespace_in_output(self):
        out = canonical_serialize(_make_row())
        assert b" " not in out
        assert b"\n" not in out

    def test_null_optional_fields_preserved(self):
        row = _make_row(score_at_decision=None, rationale=None)
        parsed = json.loads(canonical_serialize(row).decode())
        assert parsed["score_at_decision"] is None
        assert parsed["rationale"] is None

    def test_missing_required_key_raises(self):
        with pytest.raises(ValueError, match="required"):
            canonical_serialize({"portfolio_id": 1})  # type: ignore[arg-type]

    def test_invalid_type_raises(self):
        bad = _make_row()
        bad["shares"] = 10.5  # type: ignore[typeddict-item]
        with pytest.raises(ValueError, match="type"):
            canonical_serialize(bad)


# ── compute_row_hash ──────────────────────────────────────────────────

class TestComputeRowHash:
    def test_returns_64_hex_chars(self):
        h = compute_row_hash(_make_row(), GENESIS_PREV_HASH)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_matches_manual_sha256(self):
        row = _make_row()
        expected = hashlib.sha256(
            GENESIS_PREV_HASH.encode() + canonical_serialize(row)
        ).hexdigest()
        assert compute_row_hash(row, GENESIS_PREV_HASH) == expected

    def test_different_prev_hash_different_row_hash(self):
        row = _make_row()
        assert compute_row_hash(row, GENESIS_PREV_HASH) != compute_row_hash(row, "f" * 64)

    def test_different_row_different_hash(self):
        h1 = compute_row_hash(_make_row(shares="10.0000"), GENESIS_PREV_HASH)
        h2 = compute_row_hash(_make_row(shares="11.0000"), GENESIS_PREV_HASH)
        assert h1 != h2

    def test_invalid_prev_hash_length_raises(self):
        with pytest.raises(ValueError, match="hex"):
            compute_row_hash(_make_row(), "abc")

    def test_invalid_prev_hash_charset_raises(self):
        with pytest.raises(ValueError, match="hex"):
            compute_row_hash(_make_row(), "z" * 64)


# ── chain_rebalances ──────────────────────────────────────────────────

class TestChainRebalances:
    def test_happy_path_three_rows(self):
        rows = [_genesis_row(), _make_row(ticker="AAPL"), _make_row(ticker="MSFT")]
        chained = chain_rebalances(rows)
        assert len(chained) == 3
        assert chained[0].prev_hash == GENESIS_PREV_HASH
        assert chained[1].prev_hash == chained[0].row_hash
        assert chained[2].prev_hash == chained[1].row_hash

    def test_all_row_hashes_unique(self):
        rows = [_genesis_row(), _make_row(ticker="AAPL"), _make_row(ticker="MSFT")]
        chained = chain_rebalances(rows)
        assert len({c.row_hash for c in chained}) == len(chained)

    def test_empty_rows_raises(self):
        with pytest.raises(ValueError, match="empty"):
            chain_rebalances([])

    def test_first_row_not_genesis_raises(self):
        rows = [_make_row(action="BUY"), _make_row(action="BUY")]
        with pytest.raises(ValueError, match="GENESIS"):
            chain_rebalances(rows)

    def test_custom_initial_prev_hash(self):
        existing_tail = "a" * 64
        rows = [_genesis_row(), _make_row(ticker="AAPL")]
        chained = chain_rebalances(rows, initial_prev_hash=existing_tail)
        assert chained[0].prev_hash == existing_tail

    def test_single_genesis_row_produces_one_link(self):
        chained = chain_rebalances([_genesis_row()])
        assert len(chained) == 1
        assert chained[0].prev_hash == GENESIS_PREV_HASH
        assert len(chained[0].row_hash) == 64


# ── verify_chain ──────────────────────────────────────────────────────

class TestVerifyChain:
    def _build(self, n: int = 5) -> list[HashedRebalance]:
        rows = [_genesis_row()] + [_make_row(ticker=f"TCK{i}") for i in range(n - 1)]
        return chain_rebalances(rows)

    def test_valid_chain_passes(self):
        verify_chain(self._build(5))

    def test_single_row_chain_passes(self):
        verify_chain(self._build(1))

    def test_tampered_row_data_detected(self):
        chain = self._build(5)
        tampered = list(chain)
        tampered[2] = HashedRebalance(
            row=_make_row(ticker="EVIL"),
            prev_hash=chain[2].prev_hash,
            row_hash=chain[2].row_hash,
        )
        with pytest.raises(ChainBrokenError) as exc:
            verify_chain(tampered)
        assert exc.value.broken_at_index == 2

    def test_tampered_prev_hash_detected(self):
        chain = self._build(4)
        tampered = list(chain)
        tampered[2] = HashedRebalance(
            row=chain[2].row,
            prev_hash="b" * 64,
            row_hash=chain[2].row_hash,
        )
        with pytest.raises(ChainBrokenError) as exc:
            verify_chain(tampered)
        assert exc.value.broken_at_index == 2

    def test_deleted_row_breaks_chain(self):
        chain = self._build(5)
        truncated = chain[:2] + chain[3:]
        with pytest.raises(ChainBrokenError) as exc:
            verify_chain(truncated)
        assert exc.value.broken_at_index == 2

    def test_genesis_with_nonzero_prev_hash_detected(self):
        chain = self._build(3)
        tampered = list(chain)
        tampered[0] = HashedRebalance(
            row=tampered[0].row,
            prev_hash="1" * 64,
            row_hash=tampered[0].row_hash,
        )
        with pytest.raises(ChainBrokenError) as exc:
            verify_chain(tampered)
        assert exc.value.broken_at_index == 0

    def test_empty_chain_raises(self):
        with pytest.raises(ValueError, match="empty"):
            verify_chain([])


# ── Round-trip ────────────────────────────────────────────────────────

class TestChainVerifyRoundTrip:
    @pytest.mark.parametrize("n", [1, 2, 5, 20, 100])
    def test_roundtrip_various_sizes(self, n: int):
        rows = [_genesis_row()] + [
            _make_row(ticker=f"T{i}", shares=f"{i}.0000") for i in range(n - 1)
        ]
        verify_chain(chain_rebalances(rows))

    def test_roundtrip_preserves_row_content(self):
        chain = chain_rebalances([_genesis_row(), _make_row(ticker="AAPL", shares="42.1234")])
        assert chain[1].row["ticker"] == "AAPL"
        assert chain[1].row["shares"] == "42.1234"


# REMOVE AT START OF PHASE 3C ─────────────────────────────────────────
class TestNotYetImplementedSentinel:
    """Filet Phase 3B : supprimer cette classe entière au début de Phase 3C."""

    def test_canonical_serialize_not_implemented(self):
        with pytest.raises(NotImplementedError):
            canonical_serialize(_make_row())

    def test_compute_row_hash_not_implemented(self):
        with pytest.raises(NotImplementedError):
            compute_row_hash(_make_row(), GENESIS_PREV_HASH)

    def test_chain_rebalances_not_implemented(self):
        with pytest.raises(NotImplementedError):
            chain_rebalances([_genesis_row()])

    def test_verify_chain_not_implemented(self):
        with pytest.raises(NotImplementedError):
            verify_chain([])
