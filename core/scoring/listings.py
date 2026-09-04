"""
Équivalences entre cotations d'une même société — SOURCE DE VÉRITÉ UNIQUE.

Le portefeuille détient un titre sous le symbole où Max l'a réellement acheté ;
le moteur note ce titre sous la cotation qu'il analyse. Ce sont souvent deux
symboles différents pour UNE SEULE société :

    positions.actif      watchlist / scores_history
    BYDDY                1211.HK      BYD          (ADR US        vs Hong Kong)
    GOOGL                GOOG         Alphabet     (classe A      vs classe C)
    ASURB.MX             ASR          Grupo Aero.  (Mexique       vs ADR NYSE)
    RIO                  RIO.AX       Rio Tinto    (NYSE          vs ASX)

Le cockpit résout la note d'une ligne par correspondance EXACTE
(`scoreByTicker[position.actif]`). Sans ce module, ces quatre lignes
n'affichaient aucune notation : le score existait, sous un autre nom.

POURQUOI UNE ÉQUIVALENCE ET PAS UN SECOND SCORING
-------------------------------------------------
Noter les deux symboles produirait deux verdicts pour une même société. Ce
n'est pas une hypothèse : `ticker_scores` porte encore GOOG à 61 « Exceptionnel »
et GOOGL à 63 « Modéré », vestige du jour où les deux ont été notés. Une société
a une analyse, pas deux.

CE QUE L'ÉQUIVALENCE TRANSPORTE, ET CE QU'ELLE NE TRANSPORTE PAS
----------------------------------------------------------------
Les fondamentaux sont ceux de l'entreprise : identiques d'une cotation à
l'autre, ils se transportent sans réserve. Les composantes `technicals` et
`momentum` sont calculées sur la série de prix de la cotation PRINCIPALE —
celle de gauche dans la table ci-dessus. Un ADR peut en diverger légèrement
(change, liquidité, décalage de séance).

C'est assumé : une note approchée sur la bonne société vaut mieux qu'une case
vide, et mieux qu'un second score qui contredirait le premier. Les surfaces
d'affichage reçoivent `scored_as` pour pouvoir le dire.

AJOUTER UNE ÉQUIVALENCE
-----------------------
Deux conditions, toutes deux nécessaires :
  1. C'est la MÊME entreprise (cross-listing, ADR, classe d'actions) — pas une
     filiale, pas une holding, pas un ETF qui la contient.
  2. La cible est réellement notée (présente dans la watchlist SQLite).

Ce module ne sert qu'à retrouver une note existante. Il ne crée pas de note :
un titre détenu qu'aucune cotation équivalente ne couvre doit entrer dans la
watchlist, pas ici.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Racine du repo alphabrief (core/scoring/listings.py → ../../)
_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_PATH = _ROOT / "data" / "ticker_listings.json"

# symbole détenu → symbole noté. Sens unique et volontaire : on résout depuis le
# portefeuille vers l'analyse, jamais l'inverse (plusieurs cotations peuvent
# pointer vers une même analyse, la réciproque n'aurait pas de solution).
EQUIVALENCES: Dict[str, str] = {
    "BYDDY": "1211.HK",     # BYD Company — ADR américain
    "GOOGL": "GOOG",        # Alphabet — classe A vs classe C
    "ASURB.MX": "ASR",      # Grupo Aeroportuario del Sureste — ligne mexicaine
    "RIO": "RIO.AX",        # Rio Tinto — ligne NYSE vs cotation australienne
}

# Libellé de la société, pour que l'équivalence reste lisible en JSON par une
# surface qui n'a pas le contexte (et vérifiable d'un coup d'œil en revue).
COMPANIES: Dict[str, str] = {
    "BYDDY": "BYD Company",
    "GOOGL": "Alphabet",
    "ASURB.MX": "Grupo Aeroportuario del Sureste",
    "RIO": "Rio Tinto",
}


def resolve(ticker: Optional[str]) -> Optional[str]:
    """Symbole sous lequel ce titre est noté. Renvoie le ticker tel quel s'il
    n'a pas d'équivalence — la très grande majorité des cas."""
    if not ticker:
        return ticker
    return EQUIVALENCES.get(ticker.strip().upper(), ticker)


def is_alias(ticker: Optional[str]) -> bool:
    """Vrai si la note de ce ticker vient d'une autre cotation."""
    if not ticker:
        return False
    return ticker.strip().upper() in EQUIVALENCES


def describe() -> Dict[str, Any]:
    """Équivalences sérialisables — ce que consomment l'export JSON et l'API."""
    return {
        "equivalences": [
            {
                "held": held,
                "scored_as": scored,
                "company": COMPANIES.get(held, ""),
            }
            for held, scored in sorted(EQUIVALENCES.items())
        ],
        "note": (
            "Le symbole détenu et le symbole noté sont deux cotations d'une même "
            "société. Fondamentaux identiques ; technicals et momentum viennent de "
            "la cotation principale."
        ),
    }


def export(path: Path = EXPORT_PATH) -> Path:
    """Écrit les équivalences en JSON pour les consommateurs non-Python (API
    Pixel Office). Fichier GÉNÉRÉ — ne pas l'éditer à la main, éditer EQUIVALENCES."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = describe()
    payload["_generated_by"] = "core/scoring/listings.py --export"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _main(argv: List[str]) -> int:
    if "--export" in argv:
        p = export()
        print(f"équivalences écrites → {p}")
        return 0
    print(__doc__)
    for held, scored in sorted(EQUIVALENCES.items()):
        print(f"  {held:<10} → {scored:<10} {COMPANIES.get(held, '')}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
