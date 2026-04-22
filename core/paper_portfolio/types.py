"""Helpers stricts pour conversion date ↔ str ISO (pas d'heure, pas de tz).

Toute conversion aux frontières Python ↔ JSON/SQL passe par ces helpers.
"""
from __future__ import annotations

from datetime import date


def _to_iso(d: date) -> str:
    """Sérialise une date en 'YYYY-MM-DD'. Raises ValueError si datetime passé."""
    raise NotImplementedError


def _from_iso(s: str) -> date:
    """Parse 'YYYY-MM-DD' en date. Raises ValueError sur format invalide."""
    raise NotImplementedError
