"""Tests unitaires fmp_client.fmp_get.

Couvre les branches que l'audit FMP du 2026-05-22 (F4) a identifiées comme
non testées :
  - succès HTTP 200 avec payload utile
  - HTTP 429 : retry avec backoff puis abandon → None
  - HTTP 402 : remontée RequestException, retry, abandon → None
  - payload vide (HTTP 200 + []) : retourné tel quel + log evt:fmp_empty_response
  - payload "Error Message" : None

Tous les délais time.sleep sont patchés pour rester rapides.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from core.providers import fmp_client


@pytest.fixture(autouse=True)
def _reset_cache_and_counter():
    fmp_client.clear_cache()
    fmp_client._call_count = 0
    yield
    fmp_client.clear_cache()


@pytest.fixture(autouse=True)
def _no_sleep():
    """Neutralise les sleeps de throttle et de backoff pour rester rapide."""
    with patch.object(fmp_client.time, "sleep", return_value=None):
        yield


def _resp(status_code: int, payload=None, headers=None) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.status_code = status_code
    r.headers = headers or {}
    r.json.return_value = payload if payload is not None else []
    if status_code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} error", response=r,
        )
    else:
        r.raise_for_status.return_value = None
    return r


def test_success_returns_data():
    payload = [{"symbol": "AAPL", "price": 195.0}]
    with patch.object(fmp_client.requests, "get", return_value=_resp(200, payload)) as g:
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"})
    assert out == payload
    assert g.call_count == 1
    assert fmp_client.get_call_count() == 1


def test_cache_hit_avoids_second_http_call():
    payload = [{"symbol": "AAPL"}]
    with patch.object(fmp_client.requests, "get", return_value=_resp(200, payload)) as g:
        fmp_client.fmp_get("quote", {"symbol": "AAPL"})
        fmp_client.fmp_get("quote", {"symbol": "AAPL"})
    assert g.call_count == 1   # le second appel est servi par _cache


def test_http_429_retries_then_gives_up(caplog):
    caplog.set_level("WARNING")
    with patch.object(fmp_client.requests, "get", return_value=_resp(429, headers={"Retry-After": "1"})):
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"}, cache=False)
    assert out is None
    # 4 tentatives au total (MAX_RETRIES)
    assert any("fmp_429" in r.message for r in caplog.records)
    assert any("fmp_failed_429" in r.message for r in caplog.records)


def test_http_402_returns_none():
    # 402 leve raise_for_status -> RequestException -> retries -> None
    with patch.object(fmp_client.requests, "get", return_value=_resp(402)):
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"}, cache=False)
    assert out is None


def test_empty_list_response_logs_and_returns_empty(caplog):
    caplog.set_level("INFO")
    with patch.object(fmp_client.requests, "get", return_value=_resp(200, [])):
        out = fmp_client.fmp_get("income-statement", {"symbol": "1211.HK"}, cache=False)
    assert out == []
    msgs = [r.message for r in caplog.records]
    assert any('"evt": "fmp_empty_response"' in m for m in msgs)
    assert any('"symbol": "1211.HK"' in m for m in msgs)


def test_empty_dict_response_logs_and_returns_empty(caplog):
    caplog.set_level("INFO")
    with patch.object(fmp_client.requests, "get", return_value=_resp(200, {})):
        out = fmp_client.fmp_get("ratios-ttm", {"symbol": "ZZZZ"}, cache=False)
    assert out == {}
    assert any('"evt": "fmp_empty_response"' in r.message for r in caplog.records)


def test_error_message_in_json_returns_none(caplog):
    caplog.set_level("ERROR")
    payload = {"Error Message": "Invalid API key"}
    with patch.object(fmp_client.requests, "get", return_value=_resp(200, payload)):
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"}, cache=False)
    assert out is None
    assert any("fmp_api_error" in r.message for r in caplog.records)


def test_retry_after_header_respected_then_succeeds():
    # premier appel : 429 avec Retry-After:1 / second appel : 200 payload utile
    payload = [{"symbol": "AAPL"}]
    seq = [_resp(429, headers={"Retry-After": "1"}), _resp(200, payload)]
    with patch.object(fmp_client.requests, "get", side_effect=seq):
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"}, cache=False)
    assert out == payload


def test_network_error_retries_then_gives_up(caplog):
    caplog.set_level("WARNING")
    with patch.object(
        fmp_client.requests,
        "get",
        side_effect=requests.ConnectionError("boom"),
    ):
        out = fmp_client.fmp_get("quote", {"symbol": "AAPL"}, cache=False)
    assert out is None
    assert any("fmp_request_error" in r.message for r in caplog.records)
