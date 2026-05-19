from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# data/cache/ next to the project root
_BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = _BASE_DIR / "data" / "cache"

# TTL in hours per section
SECTION_TTL: Dict[str, float] = {
    "fundamentals": 24.0,
    "identity":     6.0,
    "technicals":   1.0,
    "llm":          48.0,
    "momentum":     2.0,
}


def _cache_path(ticker: str, section: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = ticker.upper().replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}_{section}.json"


def load(ticker: str, section: str) -> Optional[Dict[str, Any]]:
    """Return cached data if it exists and is still within TTL, else None."""
    path = _cache_path(ticker, section)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        ttl_hours = SECTION_TTL.get(section, 6.0)
        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600.0
        if age_hours > ttl_hours:
            logger.debug("Cache expired for %s/%s (%.1fh > %.1fh)", ticker, section, age_hours, ttl_hours)
            return None
        logger.debug("Cache HIT %s/%s (%.1fh old)", ticker, section, age_hours)
        return payload["data"]
    except Exception as e:
        logger.warning("Cache read error %s/%s: %s", ticker, section, e)
        return None


def save(ticker: str, section: str, data: Dict[str, Any]) -> None:
    """Persist data to cache."""
    path = _cache_path(ticker, section)
    try:
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.debug("Cache SAVE %s/%s", ticker, section)
    except Exception as e:
        logger.warning("Cache write error %s/%s: %s", ticker, section, e)


def invalidate(ticker: str, section: Optional[str] = None) -> None:
    """Delete cache for a ticker (one section or all)."""
    if section:
        _cache_path(ticker, section).unlink(missing_ok=True)
    else:
        safe = ticker.upper().replace("/", "_").replace("\\", "_")
        for f in CACHE_DIR.glob(f"{safe}_*.json"):
            f.unlink(missing_ok=True)
