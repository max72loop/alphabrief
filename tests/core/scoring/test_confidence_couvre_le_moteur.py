"""La confiance doit couvrir TOUT ce que lit le moteur de score.

Pourquoi ce test existe : `core/scoring/confidence.py` est une liste tenue à la
main, et elle a dérivé. Au fil des améliorations du moteur, ~17 entrées ont été
ajoutées à `compute_potential_score` sans être ajoutées à `FEATURES` — roa,
net_margin, eps_growth, current_ratio, insider/institutional ownership,
accruals_ratio, altman_z, short_interest, gross_margin_trend, price_to_ocf,
sma_50, macd_line, momentum_1m/3m/6m, tous les relative_momentum_*. Une carte
pouvait donc annoncer « confiance 96 » en ignorant un tiers de ce que le moteur
lisait réellement.

C'était supportable tant que la confiance ne servait qu'à raboter la note de
quelques pourcents. Elle commande maintenant l'ÉTIQUETTE (bands.CONFIDENCE_FLOOR
décide si la carte a le droit d'afficher un verdict) : une confiance fausse
donne un verdict à une carte creuse, ou le refuse à une carte pleine.

Le test lit la source de `compute_potential_score` plutôt que d'exécuter le
moteur : c'est le seul moyen de voir les champs qu'un chemin conditionnel
n'atteindrait pas sur une carte de test donnée.
"""

import ast
import inspect
import textwrap

from core.scoring import potential
from core.scoring.confidence import CALIBRATION_ONLY, FEATURES

# Nom de variable locale dans compute_potential_score -> section de la carte.
_ALIAS_TO_SECTION = {
    "fin": "financials",
    "val": "valuation",
    "mkt": "market",
    "tech": "technicals",
    "identity": "identity",
}


def _champs_lus_par_le_moteur() -> set[tuple[str, str]]:
    """Tous les `<alias>.get("<clef>")` de compute_potential_score."""
    source = textwrap.dedent(inspect.getsource(potential.compute_potential_score))
    tree = ast.parse(source)

    champs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            continue
        if not isinstance(func.value, ast.Name):
            continue
        section = _ALIAS_TO_SECTION.get(func.value.id)
        if section is None:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        clef = node.args[0].value
        if isinstance(clef, str):
            champs.add((section, clef))
    return champs


def test_toute_entree_du_moteur_est_comptee_par_la_confiance():
    lus = _champs_lus_par_le_moteur()
    assert lus, "l'extraction des champs a échoué — le test ne prouverait rien"

    declares = {(section, clef) for section, clef, _ in FEATURES}
    manquants = lus - declares - CALIBRATION_ONLY

    assert not manquants, (
        "Ces entrées sont lues par compute_potential_score mais ne comptent pas "
        "dans la confiance, donc une carte qui en manque peut afficher une "
        "confiance flatteuse et décrocher un verdict qu'elle ne mérite pas :\n  "
        + "\n  ".join(f"{section}.{clef}" for section, clef in sorted(manquants))
        + "\nAjoute-les à FEATURES dans core/scoring/confidence.py avec un poids "
        "reflétant leur contribution au score."
    )


def test_la_confiance_ne_compte_rien_que_le_moteur_ne_lise_pas():
    """L'inverse : une entrée retirée du moteur doit sortir de la confiance,
    sinon la couverture est plafonnée par un champ que plus personne ne remplit."""
    lus = _champs_lus_par_le_moteur()
    declares = {(section, clef) for section, clef, _ in FEATURES}
    fantomes = declares - lus

    assert not fantomes, (
        "Ces entrées comptent dans la confiance mais ne sont plus lues par le "
        "moteur — elles font baisser la couverture sans raison :\n  "
        + "\n  ".join(f"{section}.{clef}" for section, clef in sorted(fantomes))
    )
