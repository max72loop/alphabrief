"""Sage × catégories Lynch — prêt mais éteint jusqu'au verdict v2 du 19/10."""
from core.providers import sage_advisor as S


def test_eteint_par_defaut_et_prompt_v2_intact(monkeypatch):
    assert S.SAGE_LYNCH is False
    assert S.SAGE_PROMPT_VERSION == 2
    assert S._system_prompt() == S._SYSTEM_PROMPT
    assert S._lynch() == {}


def test_allume_ajoute_la_regle_avant_le_ton(monkeypatch):
    monkeypatch.setattr(S, "SAGE_LYNCH", True)
    p = S._system_prompt()
    assert "Peter Lynch" in p
    assert p.index("Peter Lynch") < p.index("- Ton direct")
    assert p.count("Peter Lynch") == 1


def test_suffixe_de_ligne():
    assert S._lynch_txt({"cle": "fast", "source": "regles:v1"}) == " · Lynch : croissance rapide (règle)"
    assert S._lynch_txt({"cle": "asset", "source": "manuel"}) == " · Lynch : valeur d'actifs (posée par Max)"
    assert S._lynch_txt(None) == ""
    assert S._lynch_txt({"cle": "inconnue"}) == ""


def test_ligne_porte_la_categorie():
    p = {"actif": "MSFT", "valeur_live_eur": 100.0, "pnl_pct": 3, "change_24h_pct": 0.5}
    txt = S._ligne_txt(p, {"libelle": "Microsoft"}, None, 1000.0, lynch={"cle": "stalwart", "source": "regles:v1"})
    assert "Lynch : valeur solide (règle)" in txt
