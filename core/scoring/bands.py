"""
Barème de notation AlphaBrief — SOURCE DE VÉRITÉ UNIQUE.

Avant ce module, le même score portait quatre verdicts contradictoires :

    core/generator.py        80 / 65 / 50 / 35 / 20   (Exceptionnel → À éviter)
    alphabrief-frontend      55 / 48 / 42 / 35        (design.ts, front Vercel)
    agents/alphabrief        60                        (alerte STRONG_BUY)
    pixel-office alphaShared 60 / 45                   (couleur de la note)

Un titre à 60 était donc simultanément « Modéré » (backend), « EXCELLENT »
(Vercel), « exceptionnel » (alerte Telegram) et vert (Pixel Office). Les seuils
backend (80, 65) étaient de surcroît inatteignables : le score n'a jamais
dépassé 68 en neuf mois de production.

Ce module remplace les quatre. Tout ce qui étiquette, colore ou alerte sur un
score AlphaBrief importe d'ici — rien ne redéfinit ses propres bornes.

CALIBRATION
-----------
Les bornes ne sont pas choisies « à la main » : ce sont des percentiles de la
distribution réellement produite par le moteur.

Calibration en vigueur — 2026-09-02, APRÈS correction des trous FMP :
198 tickers du S&P 500 tirés de façon stratifiée (18 par secteur, 11 secteurs,
seed 42) + les 37 de la watchlist = 229 sociétés distinctes, dont 173 retenues
(56 écartées par un garde-fou : sous 20 champs remplis, une carte traduit un
fetch dégradé, pas un titre mal documenté). Confiance moyenne 85,6.
Médiane 51, moyenne 51,5, min 33, max 67.

    Exceptionnel  ≥ 60   p95    top  5 %
    Fort          ≥ 56   p80        15 %
    Modéré        ≥ 50   p40        40 %
    Faible        ≥ 44   p10        30 %
    À éviter      < 44               10 %

L'échantillon est TRANSVERSAL et non temporel, à dessein. La calibration
précédente s'appuyait sur 2 795 scores, un chiffre trompeur : c'étaient 37
tickers mesurés 75 fois. La taille d'échantillon qui compte pour un barème est
le nombre de sociétés distinctes, pas le nombre de lignes en base — d'où le
passage de 37 à 173, et le tirage stratifié plutôt qu'uniforme (les bornes
sector-aware du moteur rendent le mix sectoriel déterminant).

La borne « Exceptionnel » n'a pas bougé : 60 était le p95 avant la correction
des trous, il l'est resté après. Le seuil d'alerte STRONG_BUY est donc inchangé.
Les trois autres bornes montent (54→56, 46→50, 39→44) : les titres mal
documentés ne sont plus punis deux fois, ce qui relève tout le bas de la
distribution.

Dire « ce titre est dans les 5 % les mieux notés » est vrai et actionnable.
Dire « il a 60/100 » ne l'est pas : le moteur ne distribue pas sur [0, 100].
C'est aussi pourquoi `band()` renvoie le rang en plus du label — le percentile
est l'information utile, le score brut n'est qu'un identifiant de position.

Le seuil d'alerte STRONG_BUY (60) tombe exactement sur p95. Il avait été
abaissé de 75 à 60 le 2026-05-21 pour une raison pragmatique (les alertes ne
partaient plus) ; il se trouve que c'était le bon choix. Il devient ici motivé
plutôt qu'empirique, et cesse de vivre en double dans config.json.

RECALIBRATION
-------------
    python3 -m core.scoring.bands --check      # dérive vs la distribution
    python3 -m core.scoring.bands --export     # régénère data/score_bands.json

`--check` ne modifie rien : il compare les bornes en vigueur aux percentiles
observés et signale l'écart. La décision de recalibrer reste manuelle — un
barème qui se déplace tout seul sous les pieds de l'utilisateur ne vaut pas
mieux que quatre barèmes contradictoires.

⚠ `--check` lit `scores_history` sur 90 jours glissants. Au 2026-09-02, cette
fenêtre contient encore majoritairement des scores produits AVANT la correction
des trous FMP, donc systématiquement sous-évalués. Il va donc rapporter une
dérive de plusieurs points sur les bornes basses tant que l'historique ne s'est
pas renouvelé — c'est attendu, pas un défaut de calibration. La fenêtre
redeviendra représentative vers fin septembre 2026.

Pour recalibrer avant cette date, ne pas se fier à `--check` : refaire un
échantillon transversal (S&P 500 stratifié + watchlist, cartes sous 20 champs
écartées), comme celui décrit plus haut.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Racine du repo alphabrief (core/scoring/bands.py → ../../)
_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_PATH = _ROOT / "data" / "score_bands.json"
_DB_PATH = _ROOT / "data" / "mytrader.db"

# Fenêtre de mesure servant à la calibration et au contrôle de dérive.
CALIBRATION_WINDOW_DAYS = 90

# Bornes du barème. `min_score` est inclusif ; les bandes sont ordonnées du
# meilleur au moins bon et couvrent [0, 100] sans trou ni recouvrement.
#
# `tone` est un rôle sémantique, pas une couleur : chaque surface le traduit
# dans ses propres tokens (var(--rd-ok) côté Pixel Office). Aucun code
# hexadécimal ne descend d'ici — c'est ce qui a permis au front Vercel de
# diverger sans que personne ne le voie.
BANDS: List[Dict[str, Any]] = [
    {
        "key": "exceptionnel",
        "label": "Exceptionnel",
        "min_score": 60,
        "percentile": 95,
        "share_pct": 5,
        "tone": "positive",
        "blurb": "Dans les 5 % les mieux notés — mérite un regard aujourd'hui.",
    },
    {
        "key": "fort",
        "label": "Fort",
        "min_score": 56,
        "percentile": 80,
        "share_pct": 15,
        "tone": "positive-soft",
        "blurb": "Dans le premier quintile.",
    },
    {
        "key": "modere",
        "label": "Modéré",
        "min_score": 50,
        "percentile": 40,
        "share_pct": 40,
        "tone": "neutral",
        "blurb": "Le gros du peloton — rien à signaler.",
    },
    {
        "key": "faible",
        "label": "Faible",
        "min_score": 44,
        "percentile": 10,
        "share_pct": 30,
        "tone": "warning",
        "blurb": "Sous la moyenne de l'univers suivi.",
    },
    {
        "key": "eviter",
        "label": "À éviter",
        "min_score": 0,
        "percentile": 0,
        "share_pct": 10,
        "tone": "negative",
        "blurb": "Dans les 10 % les moins bien notés.",
    },
]

# Seuil de l'alerte STRONG_BUY — la borne « Exceptionnel », pas une constante
# parallèle. Importé par agents/alphabrief/main.py.
STRONG_BUY_MIN: int = BANDS[0]["min_score"]

_UNKNOWN: Dict[str, Any] = {
    "key": "inconnu",
    "label": "N/A",
    "min_score": 0,
    "percentile": None,
    "share_pct": None,
    "tone": "muted",
    "blurb": "Pas de score disponible.",
}


def band(score: Optional[float]) -> Dict[str, Any]:
    """Bande correspondant à un score. Jamais d'exception : un score absent ou
    aberrant retombe sur la bande « inconnu », que chaque surface sait afficher."""
    if score is None:
        return dict(_UNKNOWN)
    try:
        value = float(score)
    except (TypeError, ValueError):
        return dict(_UNKNOWN)
    for b in BANDS:
        if value >= b["min_score"]:
            return dict(b)
    return dict(BANDS[-1])


def score_label(score: Optional[float]) -> str:
    """Libellé seul — remplace core.generator._score_label."""
    return band(score)["label"]


def is_strong_buy(score: Optional[float]) -> bool:
    """Vrai si le score atteint la bande « Exceptionnel » (p95)."""
    if score is None:
        return False
    try:
        return float(score) >= STRONG_BUY_MIN
    except (TypeError, ValueError):
        return False


def describe() -> Dict[str, Any]:
    """Barème sérialisable — ce que consomment l'export JSON et l'API."""
    return {
        "bands": [dict(b) for b in BANDS],
        "strong_buy_min": STRONG_BUY_MIN,
        "calibration_window_days": CALIBRATION_WINDOW_DAYS,
        "note": (
            "Bornes = percentiles de la distribution réelle du moteur. "
            "Le score ne se distribue pas sur [0, 100] : lire le rang, pas la note."
        ),
    }


def export(path: Path = EXPORT_PATH) -> Path:
    """Écrit le barème en JSON pour les consommateurs non-Python (API Pixel
    Office, front). Fichier GÉNÉRÉ — ne pas l'éditer à la main, éditer BANDS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = describe()
    payload["_generated_by"] = "core/scoring/bands.py --export"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ─────────────────────────────────────────────
# Contrôle de dérive
# ─────────────────────────────────────────────

def observed_percentiles(window_days: int = CALIBRATION_WINDOW_DAYS) -> Optional[Dict[str, Any]]:
    """Percentiles réellement observés sur la fenêtre. None si la base est
    absente ou vide — l'appelant décide quoi en faire."""
    import sqlite3

    if not _DB_PATH.exists():
        return None
    con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
    try:
        rows = [
            r[0]
            for r in con.execute(
                "SELECT score FROM scores_history "
                f"WHERE date >= date('now', '-{int(window_days)} day') AND score IS NOT NULL"
            )
        ]
    finally:
        con.close()

    if not rows:
        return None
    rows.sort()
    n = len(rows)

    def at(p: float) -> int:
        return rows[min(n - 1, max(0, int(round(p / 100 * (n - 1)))))]

    return {
        "n": n,
        "min": rows[0],
        "max": rows[-1],
        "median": at(50),
        "at": {b["key"]: at(b["percentile"]) for b in BANDS if b["percentile"]},
        "share_at_border": {
            b["key"]: round(100 * sum(1 for s in rows if s >= b["min_score"]) / n, 1)
            for b in BANDS
        },
    }


def check(window_days: int = CALIBRATION_WINDOW_DAYS) -> Dict[str, Any]:
    """Compare les bornes en vigueur aux percentiles du jour. Ne modifie rien."""
    obs = observed_percentiles(window_days)
    if obs is None:
        return {"ok": False, "reason": "pas de scores sur la fenêtre"}
    drift = []
    for b in BANDS:
        if not b["percentile"]:
            continue
        expected = obs["at"][b["key"]]
        delta = expected - b["min_score"]
        if abs(delta) >= 2:
            drift.append({
                "band": b["key"],
                "border": b["min_score"],
                "observed_at_percentile": expected,
                "delta": delta,
            })
    return {"ok": not drift, "observed": obs, "drift": drift}


def _main(argv: List[str]) -> int:
    if "--export" in argv:
        p = export()
        print(f"barème écrit → {p}")
        return 0

    if "--check" in argv:
        r = check()
        if not r.get("ok") and "reason" in r:
            print(f"⚠ {r['reason']}")
            return 1
        obs = r["observed"]
        print(f"distribution sur {CALIBRATION_WINDOW_DAYS} j : n={obs['n']} "
              f"min={obs['min']} médiane={obs['median']} max={obs['max']}")
        print()
        # « cumulé » = part de l'univers au-dessus de la borne. C'est cette
        # grandeur que le percentile promet (p95 → 5 % au-dessus), pas la part
        # de la bande prise isolément.
        print(f"{'bande':<14}{'borne':>7}{'p':>5}{'observé':>9}{'cumulé réel':>13}{'cumulé visé':>13}")
        for b in BANDS:
            share = obs["share_at_border"][b["key"]]
            seen = obs["at"].get(b["key"], "—")
            target = 100 - (b["percentile"] or 0)
            print(f"{b['label']:<14}{b['min_score']:>7}{b['percentile'] or '':>5}"
                  f"{seen:>9}{share:>12}%{target:>12}%")
        print()
        if r["drift"]:
            print("⚠ dérive ≥ 2 points — recalibration à envisager :")
            for d in r["drift"]:
                print(f"   {d['band']}: borne {d['border']} → {d['observed_at_percentile']} "
                      f"({d['delta']:+d})")
        else:
            print("✓ bornes alignées sur la distribution (dérive < 2 points)")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
