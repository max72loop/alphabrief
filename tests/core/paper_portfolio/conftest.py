"""Fixtures partagées pour tests/core/paper_portfolio/.

Session-scoped : les fichiers JSON lourds (mock_fmp_scores_sp500.json ~148KB,
mock_fmp_prices_week.json ~50KB) sont parsés UNE SEULE FOIS pour toute la
suite pytest. Économie cumulative importante sur ~100 tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "paper_portfolio"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return _FIXTURES


@pytest.fixture(scope="session")
def mock_sp500_scores() -> dict:
    return json.loads((_FIXTURES / "mock_fmp_scores_sp500.json").read_text())


@pytest.fixture(scope="session")
def mock_prices_week() -> dict:
    return json.loads((_FIXTURES / "mock_fmp_prices_week.json").read_text())


@pytest.fixture(scope="session")
def mock_benchmark() -> dict:
    return json.loads((_FIXTURES / "mock_benchmark.json").read_text())


@pytest.fixture(scope="session")
def mock_sofr() -> dict:
    return json.loads((_FIXTURES / "mock_sofr_rate.json").read_text())


@pytest.fixture(scope="session")
def mock_splits() -> dict:
    return json.loads((_FIXTURES / "mock_corporate_action_split.json").read_text())


@pytest.fixture(scope="session")
def mock_dividends() -> dict:
    return json.loads((_FIXTURES / "mock_corporate_action_dividend.json").read_text())


@pytest.fixture(scope="session")
def mock_delistings() -> dict:
    return json.loads((_FIXTURES / "mock_corporate_action_delisting.json").read_text())
