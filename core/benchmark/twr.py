"""TWR de la poche actions contre ses benchmarks (2026-10-27).

L'objectif de Sage : battre le MSCI World de +3,5 pts par an sur la poche
actions (`projects/alphabrief/PROJECT.md`). Ce module mesure les deux côtés.

TWR des LIGNES DÉTENUES, jour par jour :

    r_d = Σ q_p(d−1) · cours_p(d) / Σ q_p(d−1) · cours_p(d−1) − 1

(cours en euros, change du jour inclus). Le rendement d'un jour est celui du
portefeuille tel qu'il était la veille au soir : une ligne achetée le jour d
entre dans le calcul le lendemain, une ligne vendue en sort après son dernier
jour. Aucun flux à reconstituer, et les allers-retours avec la poche cash
(qui ne sont pas des apports au sens de `flux`) n'ont aucun effet — c'est la
mesure « stock picking contre ETF » que veut la roadmap. Les frais de
transaction ne sont pas vus (aucune donnée) : c'est un TWR brut de frais.

Benchmark : même enchaînement sur le cours en euros de l'ETF (IWDA.AS pour le
MSCI World, QQQ converti pour le Nasdaq 100, indicatif).

Pur : aucune E/S. Les cours arrivent en entrée.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

OBJECTIF_PTS_AN = 3.5          # +3,5 pts/an contre le MSCI World (décision du 2026-10-27)
GLISSANT_ANS = 3

Serie = Dict[date, float]      # date → cours en euros (clôture)


def dernier_cours(serie: Serie, d: date) -> Optional[float]:
    """Clôture du jour d, sinon la dernière connue avant (week-end, férié)."""
    if d in serie:
        return serie[d]
    avant = [k for k in serie if k <= d]
    return serie[max(avant)] if avant else None


def twr_lignes(jours: Sequence[date], quantites: Dict[str, Dict[date, float]],
               cours: Dict[str, Serie]) -> List[tuple[date, float]]:
    """Indice de valeur base 1 au premier jour, enchaîné jour par jour.

    `quantites[ticker][d]` : quantité détenue en fin de journée d (0 ou absent =
    pas détenue). `cours[ticker]` : clôtures en euros. Un jour sans aucune ligne
    évaluable la veille garde l'indice inchangé.
    """
    indice, out = 1.0, []
    for i, d in enumerate(jours):
        if i == 0:
            out.append((d, 1.0))
            continue
        veille = jours[i - 1]
        num = den = 0.0
        for t, q_par_jour in quantites.items():
            q = q_par_jour.get(veille) or 0.0
            if q <= 0:
                continue
            c0, c1 = dernier_cours(cours.get(t, {}), veille), dernier_cours(cours.get(t, {}), d)
            if c0 is None or c1 is None:
                continue
            num += q * c1
            den += q * c0
        if den > 0:
            indice *= num / den
        out.append((d, indice))
    return out


def twr_indice(jours: Sequence[date], serie: Serie) -> List[tuple[date, Optional[float]]]:
    """Même base 1 pour un benchmark : cours(d) / cours(premier jour)."""
    base = dernier_cours(serie, jours[0]) if jours else None
    return [(d, (dernier_cours(serie, d) / base) if base and dernier_cours(serie, d) else None) for d in jours]


def pct(a: Optional[float]) -> Optional[float]:
    return None if a is None else round((a - 1.0) * 100.0, 2)


def bilan(debut: date, fin: date, poche: float, monde: Optional[float], nasdaq: Optional[float]) -> Dict:
    """Écarts sur une période [debut, fin] — `poche`, `monde`, `nasdaq` : indices fin/début."""
    jours = (fin - debut).days
    p, m, n = pct(poche), pct(monde), pct(nasdaq)
    objectif = round(OBJECTIF_PTS_AN * jours / 365.0, 2)
    brut = round(p - m, 2) if p is not None and m is not None else None
    return {
        "debut": debut.isoformat(), "fin": fin.isoformat(), "jours": jours,
        "poche_pct": p, "monde_pct": m, "nasdaq_pct": n,
        "ecart_brut_pts": brut,                                   # poche − MSCI World
        "objectif_pts": objectif,                                 # +3,5 pts/an au prorata
        "ecart_objectif_pts": round(brut - objectif, 2) if brut is not None else None,
        "ecart_nasdaq_pts": round(p - n, 2) if p is not None and n is not None else None,
    }


def benchmark(jours: Sequence[date], poche: List[tuple[date, float]], monde: List[tuple[date, Optional[float]]],
              nasdaq: List[tuple[date, Optional[float]]], aujourd_hui: date) -> Dict:
    """Année civile en cours et glissant 3 ans, sur des séries de même base."""
    if len(jours) < 2:
        return {"annee": None, "glissant": None, "debut_suivi": jours[0].isoformat() if jours else None}
    idx = {d: i for i, d in enumerate(jours)}
    fin = jours[-1]

    def ratio(serie, d0, d1):
        a, b = serie[idx[d0]][1], serie[idx[d1]][1]
        return (b / a) if a and b else None

    # Année civile : depuis la dernière clôture de l'année précédente, ou depuis
    # le début du suivi s'il est plus tardif (2026 : suivi ouvert le 23/08).
    debut_annee = max(d for d in jours if d <= max(jours[0], date(fin.year - 1, 12, 31)))
    annee = bilan(debut_annee, fin, ratio(poche, debut_annee, fin), ratio(monde, debut_annee, fin), ratio(nasdaq, debut_annee, fin))
    annee["annee"] = fin.year
    annee["annee_complete"] = jours[0] <= date(fin.year - 1, 12, 31)   # suivi ouvert avant le 1er janvier

    # Glissant 3 ans : complet seulement quand le suivi a 3 ans. D'ici là on dit
    # quand il le sera, et on donne le cumul depuis le début — pas d'annualisation
    # d'une période courte, qui ferait passer deux mois de bourse pour une tendance.
    debut_3a = fin.replace(year=fin.year - GLISSANT_ANS)
    complet_le = jours[0].replace(year=jours[0].year + GLISSANT_ANS)
    if jours[0] <= debut_3a:
        d0 = max(d for d in jours if d <= debut_3a)
        g = bilan(d0, fin, ratio(poche, d0, fin), ratio(monde, d0, fin), ratio(nasdaq, d0, fin))
        ans = g["jours"] / 365.0
        for k in ("poche_pct", "monde_pct", "nasdaq_pct"):
            v = g[k]
            g[k.replace("_pct", "_pct_an")] = round(((1 + v / 100) ** (1 / ans) - 1) * 100, 2) if v is not None else None
        g["complet"] = True
    else:
        g = bilan(jours[0], fin, ratio(poche, jours[0], fin), ratio(monde, jours[0], fin), ratio(nasdaq, jours[0], fin))
        g["complet"] = False
    g["complet_le"] = complet_le.isoformat()
    return {"debut_suivi": jours[0].isoformat(), "annee": annee, "glissant": g}
