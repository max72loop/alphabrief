"""Smoke test for paper_mvp — happy path only.

Runs in isolation (no real Supabase, no real FMP). Mocks at the module-level
boundary: _fetch_quote and _supabase.

Run:  python3 -m pytest /root/agents/alphabrief/test_paper_mvp_smoke.py -v
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/root/agents/alphabrief")
sys.path.insert(0, "/root/alphabrief")
sys.path.insert(0, "/root")


class FakeQuery:
    """Minimal fluent stub of supabase-py table().select().eq()...execute().

    Records every operation in `calls` (shared list) so the test can assert
    what was issued. Configure return data via `data_map` keyed by table name."""

    def __init__(self, table: str, calls: list, data_map: dict):
        self.table = table
        self.calls = calls
        self.data_map = data_map
        self._mode = None             # 'select' | 'insert' | 'upsert' | 'update' | 'delete'
        self._payload = None
        self._filters: list[tuple] = []

    # builders
    def select(self, *a, **k):       self._mode = "select"; return self
    def insert(self, payload):       self._mode = "insert"; self._payload = payload; return self
    def upsert(self, payload, on_conflict=None):
        self._mode = "upsert"; self._payload = payload; return self
    def update(self, payload):       self._mode = "update"; self._payload = payload; return self
    def delete(self):                self._mode = "delete"; return self
    def eq(self, col, val):          self._filters.append(("eq", col, val)); return self
    def order(self, *a, **k):        return self
    def limit(self, n):              return self

    def execute(self):
        self.calls.append({
            "table": self.table, "mode": self._mode,
            "payload": self._payload, "filters": list(self._filters),
        })
        # Return-shape mimics supabase-py: object with .data
        if self._mode == "select":
            data = self.data_map.get(self.table, [])
            # Apply filters naively
            for op, col, val in self._filters:
                if op == "eq":
                    data = [r for r in data if r.get(col) == val]
            return MagicMock(data=data)
        if self._mode == "insert":
            row = dict(self._payload)
            row.setdefault("id", len(self.data_map.get(self.table, [])) + 1)
            self.data_map.setdefault(self.table, []).append(row)
            return MagicMock(data=[row])
        return MagicMock(data=[])


class FakeSupabase:
    def __init__(self, data_map: dict):
        self.calls: list = []
        self.data_map = data_map
    def table(self, name: str):
        return FakeQuery(name, self.calls, self.data_map)


def test_rebalance_smoke():
    """12 fictive tickers in ticker_scores, prices given, expect 10 BUY trades."""
    from paper_mvp import run_weekly_rebalance, FEES_BPS, INITIAL_CAPITAL, PORTFOLIO_NAME

    # 12 tickers with scores 85..74 — top 10 should be FAKE0..FAKE9
    scores_rows = [
        {"ticker": f"FAKE{i}", "score_total": 85 - i}
        for i in range(12)
    ]
    data_map = {
        "ticker_scores": scores_rows,
        "paper_portfolios": [],   # bootstrap will create
        "paper_positions": [],    # empty (first rebalance)
        "paper_rebalances": [],
        "paper_nav_history": [],
        "paper_missed_rebalances": [],
    }
    fake_sb = FakeSupabase(data_map)

    # All FMP quotes return $100 for simplicity → equipondéré exact
    def fake_quote(ticker):
        return 100.0

    with patch("paper_mvp._supabase", return_value=fake_sb), \
         patch("paper_mvp._fetch_quote", side_effect=fake_quote):
        run_weekly_rebalance()

    # ── Assertions ─────────────────────────────────────────────────────
    rebalances = [c for c in fake_sb.calls if c["table"] == "paper_rebalances" and c["mode"] == "insert"]
    assert len(rebalances) == 10, f"expected 10 BUY rows, got {len(rebalances)}"

    actions = {r["payload"]["action"] for r in rebalances}
    assert actions == {"BUY"}, f"first rebalance should be 100% BUY (no positions to sell), got {actions}"

    tickers_bought = sorted(r["payload"]["ticker"] for r in rebalances)
    expected = sorted(f"FAKE{i}" for i in range(10))
    assert tickers_bought == expected, f"top 10 mismatch: {tickers_bought} vs {expected}"

    # Equipondération: budget par position = INITIAL_CAPITAL / 10 = $10k
    # cost_factor = price * (1 + 10/10000) = 100.10
    # shares = 10000 / 100.10 ≈ 99.9001
    # gross = 99.9001 * 100 = 9990.01
    # fees = 9990.01 * 10/10000 = 9.99
    # cost = 9990.01 + 9.99 = 9999.999... ≈ 10000 ✓
    expected_shares = (INITIAL_CAPITAL / 10) / (100 * (1 + FEES_BPS / 10000))
    for r in rebalances:
        actual = r["payload"]["shares"]
        assert abs(actual - expected_shares) < 0.001, \
            f"shares for {r['payload']['ticker']}: {actual} vs expected {expected_shares}"
        assert r["payload"]["price"] == 100.0
        # fees ≈ shares * price * 10/10000
        expected_fees = expected_shares * 100 * FEES_BPS / 10000
        assert abs(r["payload"]["fees"] - expected_fees) < 0.001
        # row_hash must be present (UNIQUE constraint at DB level)
        assert r["payload"]["row_hash"] and len(r["payload"]["row_hash"]) == 64

    # paper_positions doivent avoir 10 UPSERTs LONG
    upserts = [c for c in fake_sb.calls if c["table"] == "paper_positions" and c["mode"] == "upsert"]
    assert len(upserts) == 10
    assert all(u["payload"]["side"] == "LONG" for u in upserts)

    # paper_portfolios bootstrap inséré 1 fois avec started_at fixé
    pf_inserts = [c for c in fake_sb.calls if c["table"] == "paper_portfolios" and c["mode"] == "insert"]
    assert len(pf_inserts) == 1
    assert pf_inserts[0]["payload"]["name"] == PORTFOLIO_NAME
    assert pf_inserts[0]["payload"]["initial_capital"] == INITIAL_CAPITAL
    assert pf_inserts[0]["payload"]["started_at"] is not None
