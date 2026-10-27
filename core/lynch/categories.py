"""
Les six catégories d'actions de Peter Lynch (« One Up on Wall Street ») —
une GRILLE DE LECTURE, jamais un signal. Le score n'en dépend pas.

Décisions de Max (2026-10-04) :
- des règles simples PROPOSENT une catégorie ; sa correction (`source='manuel'`)
  gagne toujours et n'est jamais écrasée (voir core/lynch/store.py) ;
- « valeur d'actifs » n'est jamais devinée : les chiffres dont on dispose ne
  voient pas les actifs cachés (immobilier, participations, trésor fiscal).

Approximation assumée : Lynch raisonne sur la croissance des BÉNÉFICES. Ici on
lit la croissance du CA sur 3 ans (`revenue_cagr_3y`, en %, 100 = +100 %/an) :
`earningsGrowth` de yfinance est un glissement trimestriel trop bruité
(285A.T à +4418 %). La règle affichée le dit.

Ce module est pur (aucun I/O hors `export`). Fichier GÉNÉRÉ pour l'API :
data/lynch_categories.json — éditer ce module, jamais le JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = 1

_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_PATH = _ROOT / "data" / "lynch_categories.json"

# Seuils de croissance annuelle du CA sur 3 ans, en %.
FAST_MIN = 20.0        # Lynch : 20-25 % par an
STALWART_MIN = 5.0     # Lynch : 10-12 % ; abaissé pour garder COST, ZTS parmi les solides
TURNAROUND_MAX = 10.0  # perte nette ET croissance sous ce seuil → redressement

# Secteurs « cycliques » au sens de Lynch (acier, chimie, pétrole, machines,
# transport). Plus étroit que core/cycle/mapping.CYCLICAL, qui range aussi la
# tech et la conso côté cyclique — juste pour la rotation sectorielle, faux ici.
CYCLICAL_SECTORS = frozenset({"Energy", "Materials", "Industrials"})

# Ordre = ordre d'affichage (du plus calme au plus spéculatif, puis les cas à part).
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "slow": {
        "label": "Croissance lente",
        "emoji": "🐢",
        "definition": "Grande société mûre qui croît à peine plus vite que l'économie ; on la garde pour le dividende.",
        "surveiller": [
            "Le dividende : versé sans interruption, et couvert par les bénéfices.",
            "La part des bénéfices distribuée : au-delà de ~70 %, le dividende devient fragile.",
            "Un cours qui a déjà bien monté : peu de potentiel au-delà, on peut alléger.",
        ],
    },
    "stalwart": {
        "label": "Valeur solide",
        "emoji": "🏛️",
        "definition": "Grande société qui croît régulièrement (~10 %/an) ; protège dans les mauvaises passes, rarement un multiple.",
        "surveiller": [
            "Le P/E par rapport à son historique : payé trop cher, même une valeur solide stagne.",
            "Gagner 30 à 50 % puis vendre pour recommencer : Lynch les fait tourner.",
            "Une diversification hasardeuse qui ralentirait la croissance.",
        ],
    },
    "fast": {
        "label": "Croissance rapide",
        "emoji": "🚀",
        "definition": "Petite ou jeune société qui croît de 20 % ou plus par an ; là sont les multiples, et les chutes.",
        "surveiller": [
            "Le PEG : un P/E au-dessus du taux de croissance, c'est payer d'avance.",
            "Que la croissance se répète ailleurs (nouveaux marchés) au lieu de s'essouffler.",
            "Le bilan : la croissance financée par la dette casse au premier trou d'air.",
        ],
    },
    "cyclical": {
        "label": "Cyclique",
        "emoji": "🔄",
        "definition": "Bénéfices qui montent et descendent avec l'économie ; tout est dans le moment.",
        "surveiller": [
            "Le piège du P/E bas : il est au plus bas au sommet du cycle, quand les bénéfices culminent.",
            "Les stocks, les prix de vente, les capacités : ils annoncent le retournement.",
            "La phase du cycle économique déclarée (onglet Marché).",
        ],
    },
    "turnaround": {
        "label": "Redressement",
        "emoji": "🩹",
        "definition": "Société en difficulté qui peut se relever ; gros gain ou perte totale.",
        "surveiller": [
            "La trésorerie face à la dette : de quoi tenir jusqu'au redressement ?",
            "Le plan : quelles activités coupées, quels coûts réduits, à quelle échéance ?",
            "Le retour aux bénéfices trimestre après trimestre (onglet Résultats).",
        ],
    },
    "asset": {
        "label": "Valeur d'actifs",
        "emoji": "💎",
        "definition": "Société assise sur des actifs que le marché ignore (immobilier, participations, trésorerie, déficits reportables).",
        "surveiller": [
            "La valeur réelle des actifs face à la capitalisation.",
            "La dette qui viendrait les grignoter.",
            "Un déclencheur : vente d'actifs, rachat, activiste.",
        ],
    },
}

KEYS = tuple(CATEGORIES)
# Seule catégorie que les règles ne proposent jamais.
MANUAL_ONLY = frozenset({"asset"})

LIMITE = (
    "Catégorie proposée à partir de la croissance du CA sur 3 ans, des pertes et du secteur. "
    "Lynch raisonne sur les bénéfices et la taille : corrige-la quand tu connais mieux la société. "
    "« Valeur d'actifs » se pose uniquement à la main."
)


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN → None


def _pct(v: float) -> str:
    return f"{v:+.1f}".replace(".", ",") + " %/an"


def classer(financials: Optional[Dict[str, Any]], secteur_gics: Optional[str]) -> Tuple[Optional[str], str]:
    """(clé de catégorie | None, règle lisible). Premier cas qui s'applique.

    Ne devine jamais : sans croissance du CA connue (et hors secteur cyclique),
    la société reste non classée.
    """
    f = financials or {}
    cagr = _num(f.get("revenue_cagr_3y"))
    net = _num(f.get("net_income"))
    perte = net is not None and net < 0
    ca = f"CA {_pct(cagr)} sur 3 ans" if cagr is not None else None

    if perte and cagr is not None and cagr < TURNAROUND_MAX:
        return "turnaround", f"perte nette et {ca}"
    if secteur_gics in CYCLICAL_SECTORS:
        return "cyclical", f"secteur {secteur_gics}"
    if cagr is None:
        return None, "croissance du CA inconnue"
    if cagr >= FAST_MIN:
        return "fast", ca + (", encore en perte" if perte else "")
    if cagr >= STALWART_MIN:
        return "stalwart", ca
    return "slow", ca


def describe() -> Dict[str, Any]:
    """Le référentiel sérialisable — ce que consomment l'export JSON et l'API."""
    return {
        "version": VERSION,
        "categories": [
            {"key": k, **v, "manual_only": k in MANUAL_ONLY} for k, v in CATEGORIES.items()
        ],
        "limite": LIMITE,
    }


def export(path: Path = EXPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = describe()
    payload["_generated_by"] = "core/lynch/categories.py --export"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _main(argv: List[str]) -> int:
    if "--export" in argv:
        print(export())
        return 0
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
