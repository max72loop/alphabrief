"""
Client FMP (Financial Modeling Prep) partagé.

Rate-limiting global (process-wide): max 1 requête en vol, délai minimum 220 ms
entre deux appels successifs (≈ 4.5 req/s, en dessous du plafond 300 req/min
du tier Starter FMP). Backoff spécifique sur HTTP 429 avec respect du header
Retry-After quand présent, sinon palier 5s / 15s / 45s sur 4 tentatives.

Chaque tentative émet un log structuré pour faciliter le debug.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)

_BASE_URL = "https://financialmodelingprep.com/stable"
_API_KEY = Config.FMP_API_KEY

# Cache mémoire (dict) — vit le temps du process, évite les appels dupliqués
_cache: Dict[str, Any] = {}

# Compteur d'appels pour monitoring
_call_count = 0

# ── Rate limiting global ─────────────────────────────────────────────────
# Sémaphore: une seule requête FMP en vol à la fois (pas de burst parallèle
# depuis le ThreadPoolExecutor du scheduler).
_fmp_gate = threading.Semaphore(1)

# Verrou + timestamp du dernier appel pour enforcer le délai minimum.
_last_call_lock = threading.Lock()
_last_call_ts = 0.0

_MIN_INTERVAL_S = 0.220   # 220 ms ≈ 4.5 req/s (limite tier Starter: 5/s = 300/min)
_MAX_RETRIES = 4
_BACKOFF_STEPS = (5, 15, 45)   # secondes, appliqué après les tentatives 1, 2, 3
_RETRY_AFTER_CAP_S = 120       # plafond au cas où FMP renvoie une valeur absurde


def _throttle() -> None:
    """Enforce un délai minimum global entre deux requêtes FMP."""
    global _last_call_ts
    with _last_call_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL_S - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()


def _parse_retry_after(resp: requests.Response) -> Optional[float]:
    """Retourne la valeur du header Retry-After en secondes, ou None."""
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        value = float(raw)
        if value < 0:
            return None
        return min(value, _RETRY_AFTER_CAP_S)
    except ValueError:
        return None


def fmp_get(endpoint: str, params: Optional[Dict[str, str]] = None, cache: bool = True) -> Any:
    """
    GET sur l'API FMP avec apikey auto-injectée.
    Retourne le JSON parsé (list ou dict) ou None en cas d'erreur persistante.
    """
    global _call_count

    url = f"{_BASE_URL}/{endpoint.lstrip('/')}"
    full_params = dict(params or {})
    full_params["apikey"] = _API_KEY

    cache_key = f"{url}?{'&'.join(f'{k}={v}' for k, v in sorted(full_params.items()) if k != 'apikey')}"
    if cache and cache_key in _cache:
        logger.debug(f"FMP cache hit: {endpoint}")
        return _cache[cache_key]

    symbol = full_params.get("symbol", "?")

    for attempt in range(_MAX_RETRIES):
        with _fmp_gate:
            _throttle()
            try:
                _call_count += 1
                resp = requests.get(url, params=full_params, timeout=15)

                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    wait = retry_after if retry_after is not None else (
                        _BACKOFF_STEPS[min(attempt, len(_BACKOFF_STEPS) - 1)]
                    )
                    logger.warning(json.dumps({
                        "evt": "fmp_429",
                        "endpoint": endpoint,
                        "symbol": symbol,
                        "attempt": attempt + 1,
                        "max_attempts": _MAX_RETRIES,
                        "wait_s": wait,
                        "retry_after_header": retry_after,
                    }))
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(wait)
                        continue
                    logger.error(json.dumps({
                        "evt": "fmp_failed_429",
                        "endpoint": endpoint,
                        "symbol": symbol,
                    }))
                    return None

                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, dict) and "Error Message" in data:
                    logger.error(json.dumps({
                        "evt": "fmp_api_error",
                        "endpoint": endpoint,
                        "symbol": symbol,
                        "message": data["Error Message"],
                    }))
                    return None

                if cache:
                    _cache[cache_key] = data
                return data

            except requests.exceptions.RequestException as e:
                wait = _BACKOFF_STEPS[min(attempt, len(_BACKOFF_STEPS) - 1)]
                logger.warning(json.dumps({
                    "evt": "fmp_request_error",
                    "endpoint": endpoint,
                    "symbol": symbol,
                    "attempt": attempt + 1,
                    "max_attempts": _MAX_RETRIES,
                    "wait_s": wait,
                    "error": str(e),
                }))
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue

    logger.error(json.dumps({
        "evt": "fmp_failed",
        "endpoint": endpoint,
        "symbol": symbol,
    }))
    return None


def clear_cache():
    """Vide le cache mémoire (utile entre deux runs de scoring)."""
    _cache.clear()


def get_call_count() -> int:
    """Retourne le nombre total d'appels FMP depuis le démarrage."""
    return _call_count
