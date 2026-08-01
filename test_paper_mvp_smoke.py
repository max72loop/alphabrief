"""Smoke test for paper_mvp — happy path only.

Tourne contre la base MIROIR (`alphabrief_mirror`), jamais contre la vraie :
`ALPHABRIEF_DSN` est positionné avant l'import de paper_mvp, et une garde
vérifie qu'on n'est pas connecté à `alphabrief`. Seul yfinance reste mocké,
parce qu'il sort de la machine.

AVANT (Supabase) ce test rejouait un faux client fluent — `FakeQuery` avec
select/insert/upsert/eq/order/limit — et n'assertait donc que sur les appels
émis, pas sur leur effet. Un ON CONFLICT mal écrit, une colonne absente, une
contrainte manquante : le mock disait OK. Une vraie base dit non.

Prérequis :  make db-reset
Run       :  python3 -m pytest /root/agents/alphabrief/test_paper_mvp_smoke.py -v
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Doit précéder l'import de paper_mvp : core.storage.db lit le DSN à l'import.
os.environ["ALPHABRIEF_DSN"] = os.environ.get(
    "ALPHABRIEF_TEST_DSN", "dbname=alphabrief_mirror"
)

sys.path.insert(0, "/root/agents/alphabrief")
sys.path.insert(0, "/root/alphabrief")
sys.path.insert(0, "/root")

from core.storage import db  # noqa: E402


@pytest.fixture(autouse=True)
def base_jetable():
    """Garde-fou + table rase.

    Un test qui écrit ne doit jamais pouvoir toucher la vraie base : c'est la
    règle posée après l'incident des objectifs de la semaine écrasés par un
    test sur la semaine en cours.
    """
    current = db.query_one("SELECT current_database() AS d")["d"]
    if current != "alphabrief_mirror":
        pytest.fail(
            f"REFUS : le test ecrit et il est connecte a '{current}'. "
            f"Attendu 'alphabrief_mirror'."
        )
    for table in ("paper_nav_history", "paper_rebalances", "paper_positions",
                  "paper_missed_rebalances", "paper_portfolios", "ticker_scores"):
        db.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
        db.execute(f"DELETE FROM {table}")
        db.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
    yield


def test_rebalance_smoke():
    """12 tickers fictifs dans ticker_scores, prix fixés, on attend 10 achats."""
    from paper_mvp import (run_weekly_rebalance, FEES_BPS, INITIAL_CAPITAL,
                           PORTFOLIO_NAME, TARGET_COUNT)

    # 12 tickers, scores 85..74 — le top 10 doit être FAKE0..FAKE9
    for i in range(12):
        db.execute(
            "INSERT INTO ticker_scores (ticker, score_total, score_fundamentals, "
            "score_technicals, score_momentum) VALUES (%s, %s, %s, %s, %s)",
            [f"FAKE{i}", 85 - i, 85 - i, 85 - i, 85 - i],
        )

    with patch("paper_mvp._fetch_quote", side_effect=lambda t: 100.0):
        run_weekly_rebalance()

    # ── Le portefeuille a été amorcé une fois ───────────────────────────
    portfolios = db.query("SELECT * FROM paper_portfolios")
    assert len(portfolios) == 1
    assert portfolios[0]["name"] == PORTFOLIO_NAME
    assert float(portfolios[0]["initial_capital"]) == INITIAL_CAPITAL
    assert portfolios[0]["started_at"] is not None

    # ── 10 achats, sur le bon top 10 ────────────────────────────────────
    trades = db.query("SELECT * FROM paper_rebalances ORDER BY ticker")
    assert len(trades) == TARGET_COUNT, f"attendu 10 lignes BUY, obtenu {len(trades)}"
    assert {t["action"] for t in trades} == {"BUY"}
    assert [t["ticker"] for t in trades] == sorted(f"FAKE{i}" for i in range(10))

    # ── Équipondération, frais compris ──────────────────────────────────
    # budget par ligne = INITIAL_CAPITAL / 10 ; cost_factor = 100 * (1 + 10/10000)
    expected_shares = (INITIAL_CAPITAL / TARGET_COUNT) / (100 * (1 + FEES_BPS / 10000))
    expected_fees = expected_shares * 100 * FEES_BPS / 10000
    for t in trades:
        assert abs(float(t["shares"]) - expected_shares) < 0.001
        assert float(t["price"]) == 100.0
        assert abs(float(t["fees"]) - expected_fees) < 0.001
        # row_hash porte une contrainte UNIQUE en base : ici c'est la base qui
        # l'aurait refusé, pas une assertion de complaisance.
        assert t["row_hash"] and len(t["row_hash"]) == 64

    # ── 10 positions ouvertes, toutes LONG ──────────────────────────────
    positions = db.query("SELECT * FROM paper_positions")
    assert len(positions) == TARGET_COUNT
    assert {p["side"] for p in positions} == {"LONG"}


def test_rebalance_est_idempotent_sur_le_top_stable():
    """Rejouer avec le même top 10 ne doit générer aucun trade supplémentaire."""
    from paper_mvp import run_weekly_rebalance, TARGET_COUNT

    for i in range(12):
        db.execute(
            "INSERT INTO ticker_scores (ticker, score_total, score_fundamentals, "
            "score_technicals, score_momentum) VALUES (%s, %s, %s, %s, %s)",
            [f"FAKE{i}", 85 - i, 85 - i, 85 - i, 85 - i],
        )

    with patch("paper_mvp._fetch_quote", side_effect=lambda t: 100.0):
        run_weekly_rebalance()
        run_weekly_rebalance()

    trades = db.query("SELECT count(*) AS n FROM paper_rebalances")[0]["n"]
    positions = db.query("SELECT count(*) AS n FROM paper_positions")[0]["n"]
    assert trades == TARGET_COUNT, f"le 2e passage a rejoue des trades : {trades}"
    assert positions == TARGET_COUNT
