"""Construit data/ombre_reference.json : distribution par secteur des quatre
métriques du score en ombre (core/scoring/ombre.py).

Échantillon : le S&P 500 du fixture, tiré de façon stratifiée (18 par secteur,
seed 42), comme la calibration du barème du 2026-09-02. Fondamentaux via le même
fournisseur que le daemon (`fetch_core_fundamentals`, yfinance derrière le
coupe-circuit FMP), sans passer par le cache des cartes.

Usage : python3 scripts/reference_ombre.py   (écrit seulement le JSON)
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.providers.fundamentals_yf import fetch_core_fundamentals  # noqa: E402
from core.scoring import ombre  # noqa: E402
from core.scoring.secteur import secteur_moteur  # noqa: E402

UNIVERS = ROOT / "tests/fixtures/paper_portfolio/data/sp500_tickers.csv"
PAR_SECTEUR = 18
SEED = 42


def echantillon() -> list[tuple[str, str]]:
    par_secteur = defaultdict(list)
    with UNIVERS.open() as f:
        for r in csv.DictReader(f):
            par_secteur[r["sector"]].append(r["ticker"].replace(".", "-"))
    rng = random.Random(SEED)
    out = []
    for secteur in sorted(par_secteur):
        tickers = sorted(par_secteur[secteur])
        for t in rng.sample(tickers, min(PAR_SECTEUR, len(tickers))):
            out.append((t, secteur_moteur(secteur)))
    return out


def main() -> None:
    dist: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    ech = echantillon()
    retenus = 0
    for i, (ticker, secteur) in enumerate(ech, 1):
        try:
            payload = fetch_core_fundamentals(ticker)
        except Exception as e:  # un titre qui échoue ne doit pas arrêter l'échantillon
            print(f"[{i}/{len(ech)}] {ticker}: échec ({e})", file=sys.stderr)
            continue
        valeurs = ombre.metriques(payload)
        n = sum(v is not None for v in valeurs.values())
        print(f"[{i}/{len(ech)}] {ticker:<6} {secteur:<24} {n}/4", file=sys.stderr)
        if n < 2:
            continue
        retenus += 1
        for nom, v in valeurs.items():
            if v is not None:
                dist[secteur][nom].append(v)
                dist["_tous"][nom].append(v)

    sortie = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": ombre.VERSION,
        "echantillon": f"S&P 500 stratifié {PAR_SECTEUR}/secteur seed {SEED} : {retenus}/{len(ech)} retenus",
        "secteurs": {s: {m: sorted(v) for m, v in ms.items()} for s, ms in dist.items()},
    }
    ombre.REFERENCE_PATH.write_text(json.dumps(sortie, ensure_ascii=False, indent=1))
    print(sortie["echantillon"])


if __name__ == "__main__":
    main()
