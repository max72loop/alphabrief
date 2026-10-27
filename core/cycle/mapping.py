"""
Rotation sectorielle — secteur GICS → phase du cycle où il a historiquement
surperformé (Stovall, repris par Fidelity). SOURCE DE VÉRITÉ UNIQUE.

C'est une constante de code, pas une table : elle change rarement, elle doit
se relire et se differ dans une revue, et personne ne doit pouvoir la modifier
depuis un écran. `export()` la sérialise en JSON pour l'API Pixel Office, comme
`core/scoring/listings.py` — le JSON est GÉNÉRÉ, on édite ce fichier.

CE QUE C'EST, ET CE QUE CE N'EST PAS
------------------------------------
Une grille de lecture : « mon exposition actions ressemble-t-elle à ce que le
modèle attend pour la phase que j'ai déclarée ? ». Aucun signal d'achat ni de
vente n'en sort, aucun ordre n'en dépend.

Le modèle est FAIBLEMENT VALIDÉ, et toute surface qui l'affiche le dit en
clair (LIMITE ci-dessous) — pas en note de bas de page repliée :
  · Molchanov, IJFE 2024 — 15 cycles de 1948 à 2022 : un investisseur qui
    daterait parfaitement les phases ne tire que 0,16 % par mois de rendement
    ajusté du risque, avant frais.
  · Stangl, Jacobsen & Visaltanachoti (2009) — 2,3 % de sous-performance
    annuelle contre le S&P 500 sur 1948-2007.

Les quatre phases portent les MÊMES clés que le détecteur de marché
(core/bitcoin/cycle_detector.py) : `recovery`, `expansion`, `slowdown`,
`recession`. Une lecture marché et une phase déclarée se comparent donc sans
table de correspondance — mais le libellé de `slowdown` est ici « Fin de
cycle », le mot du modèle sectoriel, là où le détecteur dit « Ralentissement ».

La bourse anticipe l'économie de 6 à 9 mois : la phase boursière précède la
phase macro. La phase à déclarer est celle du MARCHÉ, pas celle du PIB.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Date de la dernière modification de la table. À bumper à chaque changement
# du mapping : c'est ce qui permet à une lecture archivée de dire sous quelle
# version elle a été produite.
VERSION = "2026-09-19"

_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_PATH = _ROOT / "data" / "cycle_mapping.json"


# ── Les onze secteurs GICS ──────────────────────────────────
# Clé = nom GICS officiel, tel qu'il est stocké dans societes.secteur_gics.
# La contrainte CHECK de la migration 2026_09_19_cycle.sql liste exactement
# ces onze noms — verrouillé par tests/core/cycle/test_mapping.py.
SECTORS: Dict[str, str] = {
    "Consumer Discretionary": "Consommation discrétionnaire",
    "Financials":             "Financières",
    "Real Estate":            "Immobilier",
    "Industrials":            "Industrielles",
    "Information Technology": "Technologie",
    "Communication Services": "Communication",
    "Energy":                 "Énergie",
    "Materials":              "Matériaux",
    "Health Care":            "Santé",
    "Consumer Staples":       "Consommation de base",
    "Utilities":              "Services aux collectivités",
}

# Cyclique / défensif — le partage binaire classique : les trois secteurs dont
# la demande ne suit pas le cycle (on mange, on se soigne, on s'éclaire en
# récession aussi) sont défensifs, les huit autres sont cycliques. Communication
# Services est classé cyclique parce que, depuis la refonte GICS de 2018, il
# porte surtout médias et plateformes (Alphabet, Meta), pas les télécoms — c'est
# ce qui explique qu'il figure à la fois en Expansion et en Récession dans la
# table : la ligne « Récession » vise sa part télécoms.
DEFENSIVE: frozenset = frozenset({"Consumer Staples", "Health Care", "Utilities"})
CYCLICAL: frozenset = frozenset(SECTORS) - DEFENSIVE


# ── Les quatre phases, dans l'ordre du cycle ────────────────
# Chaque phase : libellé, lecture macro (une phrase), secteurs en tête.
# `faible_discrimination` marque l'Expansion : c'est la phase la plus longue du
# cycle et celle où la dispersion entre secteurs est la plus faible — l'écart
# d'exposition y est donc peu informatif, et la surface le dit comme tel.
PHASES: Tuple[Dict[str, Any], ...] = (
    {
        "key": "recovery",
        "label": "Reprise",
        "macro": "Taux bas, le crédit repart, marges en expansion.",
        "leaders": ("Consumer Discretionary", "Financials", "Real Estate", "Industrials"),
        "faible_discrimination": False,
    },
    {
        "key": "expansion",
        "label": "Expansion",
        "macro": "Croissance modérée mais installée, politique neutre, profits sains.",
        "leaders": ("Information Technology", "Communication Services", "Industrials", "Consumer Discretionary"),
        "faible_discrimination": True,
    },
    {
        "key": "slowdown",
        "label": "Fin de cycle",
        "macro": "Surchauffe, inflation au-dessus de la tendance, le crédit se resserre.",
        "leaders": ("Energy", "Materials", "Health Care", "Consumer Staples"),
        "faible_discrimination": False,
    },
    {
        "key": "recession",
        "label": "Récession",
        "macro": "Contraction, performance globale négative.",
        "leaders": ("Consumer Staples", "Health Care", "Utilities", "Communication Services"),
        "faible_discrimination": False,
    },
)

PHASE_KEYS: Tuple[str, ...] = tuple(p["key"] for p in PHASES)
LEADERS: Dict[str, Tuple[str, ...]] = {p["key"]: p["leaders"] for p in PHASES}

# La limite empirique, mot pour mot ce qu'affiche toute surface du module.
LIMITE = (
    "Modèle faiblement validé : sur 15 cycles (1948-2022), dater parfaitement "
    "les phases ne rapporte que 0,16 % par mois ajusté du risque avant frais "
    "(Molchanov, IJFE 2024) ; Stangl et al. (2009) mesurent 2,3 % de "
    "sous-performance annuelle contre le S&P 500 sur 1948-2007. "
    "Grille de lecture, pas un signal."
)

MID_CYCLE_NOTE = (
    "Expansion : phase la plus longue du cycle et dispersion entre secteurs la "
    "plus faible — l'écart d'exposition y est peu informatif."
)


# ── Normalisation des libellés fournisseurs ─────────────────
# FMP (`/profile`) et yfinance (`Ticker.info["sector"]`, taxonomie Morningstar)
# ne parlent pas GICS : « Technology », « Financial Services », « Consumer
# Cyclical », « Healthcare », « Basic Materials »… Correspondance 1:1 au niveau
# secteur ; une société précise peut être rangée ailleurs par S&P (Uber est
# « Technology » chez Morningstar, Industrials en GICS) — c'est la tolérance
# assumée d'une grille de lecture, et `secteur_source` garde la trace.
_ALIASES: Dict[str, str] = {
    "technology":               "Information Technology",
    "information technology":   "Information Technology",
    "financial services":       "Financials",
    "financial":                "Financials",
    "financials":               "Financials",
    "consumer cyclical":        "Consumer Discretionary",
    "consumer discretionary":   "Consumer Discretionary",
    "consumer defensive":       "Consumer Staples",
    "consumer staples":         "Consumer Staples",
    "healthcare":               "Health Care",
    "health care":              "Health Care",
    "basic materials":          "Materials",
    "materials":                "Materials",
    "communication services":   "Communication Services",
    "telecommunications":       "Communication Services",
    "industrials":              "Industrials",
    "energy":                   "Energy",
    "utilities":                "Utilities",
    "real estate":              "Real Estate",
}


def normalize_sector(raw: Optional[str]) -> Optional[str]:
    """Libellé fournisseur → nom GICS, ou None si inconnu (jamais une devinette)."""
    if not raw:
        return None
    return _ALIASES.get(str(raw).strip().lower())


def phase_info(key: Optional[str]) -> Optional[Dict[str, Any]]:
    for p in PHASES:
        if p["key"] == key:
            return p
    return None


def describe() -> Dict[str, Any]:
    """Le mapping sérialisable — ce que consomment l'export JSON et l'API."""
    return {
        "version": VERSION,
        "sectors": [
            {
                "key": name,
                "label": label,
                "nature": "defensif" if name in DEFENSIVE else "cyclique",
            }
            for name, label in SECTORS.items()
        ],
        "phases": [
            {
                "key": p["key"],
                "label": p["label"],
                "macro": p["macro"],
                "leaders": list(p["leaders"]),
                "faible_discrimination": p["faible_discrimination"],
            }
            for p in PHASES
        ],
        "limite": LIMITE,
        "mid_cycle_note": MID_CYCLE_NOTE,
    }


def export(path: Path = EXPORT_PATH) -> Path:
    """Écrit le mapping en JSON pour les consommateurs non-Python (API Pixel
    Office). Fichier GÉNÉRÉ — ne pas l'éditer à la main, éditer ce module."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = describe()
    payload["_generated_by"] = "core/cycle/mapping.py --export"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _main(argv: List[str]) -> int:
    if "--export" in argv:
        p = export()
        print(f"mapping écrit → {p}")
        return 0
    print(__doc__)
    for p in PHASES:
        print(f"  {p['label']:<14} {', '.join(SECTORS[s] for s in p['leaders'])}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
