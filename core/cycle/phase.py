"""
La phase du cycle DÉCLARÉE par Max — datée, ou absente. Jamais devinée.

Le détecteur de marché (core/bitcoin/cycle_detector.py) vote une phase depuis
onze indicateurs de prix ; c'est une lecture, pas une déclaration. Les entrées
macro que le modèle attend (courbe 10 ans − 3 mois, ISM manufacturier,
chômage, CPI core) ne sont pas branchées : tant qu'elles ne le sont pas, la
phase retenue par la grille de lecture est celle que Max déclare ici, avec sa
date affichée partout où elle sert. Une phase non datée est une phase fausse.

Journal en ajout seul (`cycle_phase_declarations`) : la dernière ligne fait
foi, les précédentes restent lisibles — on peut toujours répondre à « qu'est-ce
que je pensais en juin ? ».
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from core.cycle.mapping import PHASE_KEYS, phase_info
from core.storage import db


def declaree() -> Optional[Dict[str, Any]]:
    """La dernière déclaration : {phase, label, declared_at} — ou None."""
    row = db.query_one(
        "SELECT phase, declared_at FROM cycle_phase_declarations "
        " ORDER BY declared_at DESC, id DESC LIMIT 1"
    )
    if not row:
        return None
    info = phase_info(row["phase"]) or {}
    return {
        "phase": row["phase"],
        "label": info.get("label", row["phase"]),
        "declared_at": row["declared_at"],
    }


def declarer(phase: str) -> Dict[str, Any]:
    """Ajoute une déclaration datée `now()`. Refuse tout ce qui n'est pas une
    des quatre phases — avant même la contrainte CHECK, pour un message clair."""
    if phase not in PHASE_KEYS:
        raise ValueError(f"phase inconnue : {phase!r} (attendu : {', '.join(PHASE_KEYS)})")
    db.execute("INSERT INTO cycle_phase_declarations (phase) VALUES (%s)", [phase])
    d = declaree()
    assert d is not None
    return d


def ligne_rappel() -> str:
    """La ligne du rappel hebdomadaire — « phase déclarée le JJ/MM », rien de plus."""
    d = declaree()
    if d is None:
        return "Phase du cycle : aucune déclarée"
    # Le jour affiché est celui de Paris, pas celui du serveur : une
    # déclaration à 00h30 heure locale n'est pas « d'hier ».
    quand = d["declared_at"].astimezone(ZoneInfo("Europe/Paris"))
    return f"Phase du cycle : {d['label']}, déclarée le {quand:%d/%m}"
