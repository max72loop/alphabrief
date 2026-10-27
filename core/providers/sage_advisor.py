from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Script de cotations live, déjà écrit et déjà utilisé par l'API Pixel Office
# (api/lib/alphabrief_live.js). Lecture seule, ~9 s. Sage tourne une fois par
# jour à 8h : on l'appelle en direct plutôt que de dupliquer la logique yfinance
# + conversion de devise dans un deuxième endroit.
POSITIONS_SCRIPT = "/root/agents/alphabrief/scripts/positions_dashboard.py"
POSITIONS_TIMEOUT = 40

# Large volontairement : le message fait quatre lignes, mais le budget sert de
# marge, pas de cible. Voir le commentaire de l'appel LLM.
MAX_TOKENS = 600

# Version du prompt, écrite dans chaque ligne du carnet (`sage_journal.prompt_version`).
# v1 = jusqu'au 2026-09-29 (une ligne de phase, celle du détecteur). v2 = 2026-09-30 :
# phase déclarée + grille sectorielle. Le moratoire « pas de levier avant le verdict
# du 19/10 » a été levé par Max ; la colonne permet de juger les deux versions
# séparément plutôt qu'un carnet mélangé. Toute réécriture du prompt l'incrémente.
#
# Catégories de Peter Lynch (2026-10-04) : code PRÊT mais ÉTEINT. Max a choisi de
# ne pas couper l'évaluation de la v2 avant son verdict du 19/10. L'allumer, c'est
# passer en v3 (le carnet sépare alors les deux périodes).
SAGE_LYNCH = False
SAGE_PROMPT_VERSION = 3 if SAGE_LYNCH else 2

# Sage ne parle qu'à Max, de l'argent de Max, dans le Telegram de Max.
#
# L'ancienne consigne interdisait tout vocabulaire d'achat/vente : elle venait
# de prompt_agent.txt, écrit du temps où AlphaBrief était un SaaS servi à des
# tiers — situation où le conseil en investissement est réglementé en France.
# Ce SaaS est décommissionné (2026-09-04, frontend supprimé, user_id droppée).
# Il ne reste qu'un outil personnel qui commente le portefeuille de son
# propriétaire ; la contrainte n'a plus d'objet, et elle empêchait Sage de dire
# la seule chose que Max lui demande : quoi acheter, quoi vendre, ou rien.
_SYSTEM_PROMPT = (
    "Tu es Sage, la voix qui regarde le portefeuille de Max chaque matin. "
    "Tu parles à Max seul, de ses propres lignes, dans un outil qui n'appartient "
    "qu'à lui — tu peux donc nommer une ligne à acheter et une ligne à vendre, "
    "sans détour et sans avertissement juridique.\n"
    "Règles :\n"
    "- Au plus UNE idée à l'achat et UNE idée à la vente. Jamais de liste.\n"
    "- Chaque idée nomme la ligne et donne SA raison en une phrase, tirée des "
    "chiffres fournis (note, poids, plus-value, cash disponible).\n"
    "- « Rien à faire aujourd'hui » est une bonne réponse, et c'est la plus "
    "fréquente : ne fabrique pas un mouvement pour avoir quelque chose à dire.\n"
    "- Le cash disponible est une contrainte dure : si un achat le dépasse, dis "
    "explicitement quelle ligne le finance.\n"
    "- Commence par l'idée qui compte. Si les deux côtés sont vides, dis-le en "
    "une phrase et arrête-toi là.\n"
    "- Pas de récapitulatif du portefeuille, pas de phrase de conclusion qui "
    "répète ce qui vient d'être dit.\n"
    "- Quand une ligne porte une thèse de Max, elle prime : ne propose sa vente "
    "que si tu peux nommer, dans les chiffres fournis, ce qui la contredit — et "
    "dis-le explicitement (« ta thèse dit …, la note dit … »). Sans thèse, tu "
    "juges sur les chiffres seuls.\n"
    "- La phase de cycle est une grille de lecture à l'effet mesuré faible : "
    "elle ne justifie JAMAIS seule un achat ou une vente. Elle peut départager "
    "deux lignes proches, ou appuyer une raison déjà tirée des chiffres. En "
    "Expansion, elle ne départage presque rien. Si la phase déclarée par Max et "
    "le détecteur divergent, c'est la phase déclarée qui sert de grille.\n"
    "- Ton direct, personnel, en français. Pas de préambule, pas de guillemets, "
    "pas de chiffres recopiés en vrac. 3 lignes, 4 au maximum.\n"
    "- Après le message, sur UNE dernière ligne seule et exactement dans cette "
    "forme, ton verdict lisible par la machine : "
    '{"achat": "TICKER" ou null, "vente": "TICKER" ou null, "raison": "80 caractères max"}. '
    "TICKER = le symbole tel qu'il apparaît entre parenthèses dans les lignes ou "
    "les candidats. Rien après cette ligne."
)

# Ajoutée aux règles quand SAGE_LYNCH est allumé (voir _system_prompt).
_REGLE_LYNCH = (
    "- La catégorie de Peter Lynch d'une ligne (croissance lente, valeur solide, "
    "croissance rapide, cyclique, redressement, valeur d'actifs) est une grille de "
    "lecture, jamais une raison suffisante d'acheter ou de vendre. Elle dit quoi "
    "regarder : le PEG pour une croissance rapide, le P/E et le dividende pour une "
    "valeur solide ou lente, le moment du cycle pour une cyclique, la trésorerie "
    "pour un redressement. « posée par Max » = Max l'a choisie lui-même.\n"
)


def _system_prompt() -> str:
    if not SAGE_LYNCH:
        return _SYSTEM_PROMPT
    # Juste avant la règle de ton, avec les autres grilles de lecture.
    ancre = "- Ton direct, personnel, en français."
    return _SYSTEM_PROMPT.replace(ancre, _REGLE_LYNCH + ancre, 1)


# Le verdict structuré est retiré du message avant Telegram (voir
# _extraire_verdict) : Max lit le texte, le carnet lit la ligne.

_USER_TEMPLATE = """\
Portefeuille de Max ce matin — {total_eur} € au total, dont {cash_eur} € de cash disponible.
Tolérance au risque affichée (1=prudent, 5=agressif) : {risk}/5.

Lignes détenues (poids · plus-value depuis l'entrée · variation 24h · note AlphaBrief sur 100 · secteur) :
{lignes}

Suivies mais pas détenues, les mieux notées :
{candidats}

Cycle économique — grille de lecture, pas un signal :
{cycle}

Hier tu as dit : {hier}
Si l'idée d'hier tient toujours, dis-le en une ligne sans la redévelopper ; si tu changes d'avis, dis pourquoi en une phrase.

Écris le message du matin.
"""


def _extraire_verdict(raw: str) -> tuple[str, Optional[Dict[str, Any]]]:
    """Sépare le message du verdict JSON que Sage ajoute en dernière ligne.

    Tolérant par construction : si la ligne manque ou ne se parse pas, le
    message part tel quel et le verdict vaut None — un détail de format ne
    doit jamais faire taire Sage. Ne regarde que la DERNIÈRE ligne commençant
    par « { » : le texte au-dessus est intouché, et ce qui suivrait (le modèle
    désobéit parfois) est jeté avec elle."""
    lignes = raw.rstrip().split("\n")
    for i in range(len(lignes) - 1, -1, -1):
        ligne = lignes[i].strip()
        if not ligne.startswith("{"):
            continue
        try:
            data = json.loads(ligne)
        except json.JSONDecodeError:
            logger.warning("Sage: ligne de verdict illisible, message envoyé sans verdict")
            return raw.strip(), None
        if not isinstance(data, dict):
            return raw.strip(), None

        def norm(v: Any) -> Optional[str]:
            return str(v).strip().upper() if isinstance(v, str) and v.strip() else None

        verdict = {
            "achat": norm(data.get("achat")),
            "vente": norm(data.get("vente")),
            "raison": (str(data.get("raison") or "").strip()[:120] or None),
        }
        return "\n".join(lignes[:i]).strip(), verdict
    return raw.strip(), None


def _fmt_eur(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _positions_live() -> List[dict]:
    """Lignes live (valeur, P&L, variation 24h) par position. [] si indisponible."""
    try:
        out = subprocess.run(
            ["python3", POSITIONS_SCRIPT],
            cwd=os.path.dirname(POSITIONS_SCRIPT),
            capture_output=True,
            text=True,
            timeout=POSITIONS_TIMEOUT,
            check=True,
        ).stdout
        rows = json.loads(out)
        return rows if isinstance(rows, list) else []
    except Exception as e:
        logger.warning(f"Sage: cotations live indisponibles ({e})")
        return []


def _valeur(p: dict) -> float:
    """Valeur d'une ligne, cotation d'abord, dernière saisie ensuite.

    Le cash n'a pas de cours (yfinance ne connaît pas CASH-EUR) et rendrait
    `valeur_live_eur` null : sans ce repli, la poche de cash disparaît du total
    ET de la contrainte d'achat — Sage proposerait des achats sans savoir avec
    quoi. C'est le même repli que l'API Pixel Office fait pour son total live.
    """
    for cle in ("valeur_live_eur", "derniere_valeur_eur"):
        v = p.get(cle)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


# Une note qui porte cette bande n'est pas un verdict : elle dit qu'on n'en sait
# pas assez (bands.CONFIDENCE_FLOOR). Le nombre reste élevé — CS.PA sort à 70/100
# « Données insuffisantes » — donc un classement par score seul mettrait en tête
# des idées d'achat précisément les sociétés sur lesquelles le moteur se tait.
BANDE_SANS_VERDICT = "données insuffisantes"


def _sans_verdict(score: Optional[dict]) -> bool:
    return (score or {}).get("score_label", "").strip().lower() == BANDE_SANS_VERDICT


def _libelles() -> Dict[int, dict]:
    """position_id → libellé + classe, pour nommer les lignes en clair."""
    try:
        from core.storage import db

        rows = db.query(
            "SELECT id, actif, libelle, classe FROM positions WHERE ouverte"
        )
        return {int(r["id"]): r for r in rows}
    except Exception as e:
        logger.warning(f"Sage: libellés positions indisponibles ({e})")
        return {}


def _scores() -> Dict[str, dict]:
    """Dernier score connu par ticker. {} si la base ne répond pas."""
    try:
        from core.storage import db

        rows = db.query(
            "SELECT DISTINCT ON (ticker) ticker, score_total, score_label "
            "FROM ticker_scores ORDER BY ticker, score_date DESC"
        )
        return {r["ticker"]: r for r in rows}
    except Exception as e:
        logger.warning(f"Sage: scores indisponibles ({e})")
        return {}


THESE_MAX = 140


def _theses() -> Dict[str, str]:
    """Thèses écrites par Max (societes.these, clé = ticker NOTÉ). {} si la
    base ne répond pas — Sage juge alors sur les chiffres seuls, sans le dire."""
    try:
        from core.storage import db

        rows = db.query("SELECT ticker, these FROM societes WHERE these IS NOT NULL AND these <> ''")
        return {r["ticker"].upper(): r["these"].strip() for r in rows if r["these"].strip()}
    except Exception as e:
        logger.warning(f"Sage: thèses indisponibles ({e})")
        return {}


def _these_txt(these: Optional[str], prefixe: str = "thèse de Max") -> str:
    if not these:
        return ""
    court = these if len(these) <= THESE_MAX else these[: THESE_MAX - 1].rstrip() + "…"
    return f" · {prefixe} : « {court} »"


def _secteur_txt(secteur: Optional[str], phase_key: Optional[str]) -> str:
    """« · secteur Technologie · en tête dans cette phase ». Vide pour ce qui
    n'a pas de secteur (crypto, ETF, cash) ou un libellé inconnu : on ne range
    jamais une ligne au hasard. Le « en tête » n'existe que si une phase est
    déclarée — sans phase, pas de croisement."""
    from core.cycle import mapping

    gics = secteur if secteur in mapping.SECTORS else mapping.normalize_sector(secteur)
    if not gics:
        return ""
    txt = f" · secteur {mapping.SECTORS[gics]}"
    if phase_key and gics in mapping.LEADERS.get(phase_key, ()):
        txt += " · en tête dans cette phase"
    return txt


def _secteurs_notes() -> Dict[str, str]:
    """{ticker noté → GICS} pour les candidats, qui n'ont pas de ligne live.
    Vide si la base ne répond pas : Sage parle sans secteur plutôt que pas du tout."""
    try:
        from core.cycle.secteurs import par_ticker
        return par_ticker()
    except Exception as e:
        logger.warning(f"Sage: secteurs des candidats indisponibles ({e})")
        return {}


def _lynch() -> Dict[str, dict]:
    """{ticker noté → {cle, source}} — vide si SAGE_LYNCH est éteint ou si la
    base ne répond pas : Sage parle alors sans catégorie, sans le dire."""
    if not SAGE_LYNCH:
        return {}
    try:
        from core.lynch.store import par_ticker
        return par_ticker()
    except Exception as e:
        logger.warning(f"Sage: catégories Lynch indisponibles ({e})")
        return {}


def _lynch_txt(lynch: Optional[dict]) -> str:
    from core.lynch.categories import CATEGORIES

    cat = CATEGORIES.get((lynch or {}).get("cle"))
    if not cat:
        return ""
    qui = "posée par Max" if lynch.get("source") == "manuel" else "règle"
    return f" · Lynch : {cat['label'].lower()} ({qui})"


def _ligne_txt(
    p: dict, meta: dict, score: Optional[dict], total: float,
    these: Optional[str] = None, phase_key: Optional[str] = None,
    lynch: Optional[dict] = None,
) -> str:
    nom = (meta.get("libelle") or p.get("actif") or "?").strip()
    poids = _valeur(p) / total * 100 if total else 0
    note = (
        f"note {int(score['score_total'])}/100 ({score['score_label']})"
        if score
        else "pas de note"
    )
    return (
        f"- {nom} ({p.get('actif')}) : {_fmt_eur(_valeur(p))} € · "
        f"{poids:.0f}% du portefeuille · "
        f"P&L {p.get('pnl_pct', 0):+.0f}% · 24h {p.get('change_24h_pct', 0):+.1f}% · {note}"
        f"{_secteur_txt(p.get('secteur_gics'), phase_key)}"
        f"{_lynch_txt(lynch)}"
        f"{_these_txt(these)}"
    )


def _contexte(
    agent_pref: Dict[str, Any], cycle: Optional[str] = None, hier: Optional[str] = None,
    phase_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Assemble ce que Sage doit avoir sous les yeux. None si le portefeuille
    n'est pas lisible — mieux vaut se taire qu'un conseil sur des chiffres faux.

    C'est aussi ce qui remplace l'ancienne entrée `total_eur` de /api/patrimoine :
    ce total ne compte que les supports saisis récemment, et vaut donc 10 € un
    jour où la saisie consolidée a quinze jours (constaté le 2026-09-08, avec une
    « variation » de −10 938 €). Le total live, lui, décrit le portefeuille réel.
    """
    positions = _positions_live()
    if not positions:
        return None

    metas = _libelles()
    scores = _scores()
    total = sum(_valeur(p) for p in positions)
    if total <= 0:
        logger.warning("Sage: total live nul, message du jour annulé")
        return None

    detenues, cash = [], 0.0
    for p in positions:
        meta = metas.get(int(p.get("position_id", 0)), {})
        if (meta.get("classe") or "").lower() == "cash":
            cash += _valeur(p)
            continue
        detenues.append((p, meta))

    detenues.sort(key=lambda t: _valeur(t[0]), reverse=True)

    # Le portefeuille détient un titre sous le symbole où Max l'a acheté, le
    # moteur le note sous la cotation qu'il analyse : BYDDY→1211.HK, GOOGL→GOOG,
    # ASURB.MX→ASR, RIO→RIO.AX. Sans cette résolution, quatre lignes détenues
    # arrivaient « sans note » ET leur société revenait dans les candidats à
    # l'achat — Sage aurait proposé d'acheter ce que Max détient déjà.
    from core.scoring.listings import resolve

    # La thèse de Max voyage avec la ligne (2026-09-18) : Sage ne doit pas
    # proposer de vendre ce que Max a écrit vouloir garder sans le savoir.
    theses = _theses()
    lynch = _lynch()
    notes = {p.get("actif"): scores.get(resolve(p.get("actif"))) for p, _ in detenues}
    lignes = [
        _ligne_txt(
            p, meta, notes.get(p.get("actif")), total,
            theses.get((resolve(p.get("actif")) or "").upper()), phase_key,
            lynch.get((resolve(p.get("actif")) or "").upper()),
        )
        for p, meta in detenues
    ]

    analyses_tenues = {resolve(p.get("actif")) for p, _ in detenues}
    candidats = sorted(
        (
            s
            for t, s in scores.items()
            if t not in analyses_tenues and not _sans_verdict(s)
        ),
        key=lambda s: float(s["score_total"]),
        reverse=True,
    )[:5]
    secteurs = _secteurs_notes() if candidats else {}

    return {
        "total_eur": total,
        "cash_eur": cash,
        "risk": agent_pref.get("risk", 3),
        "lignes": "\n".join(lignes),
        "candidats": "\n".join(
            f"- {c['ticker']} : note {int(c['score_total'])}/100 ({c['score_label']})"
            f"{_secteur_txt(secteurs.get(str(c['ticker']).upper()), phase_key)}"
            f"{_lynch_txt(lynch.get(str(c['ticker']).upper()))}"
            f"{_these_txt(theses.get(str(c['ticker']).upper()), 'thèse')}"
            for c in candidats
        )
        or "- aucune",
        # Formatés par le daemon, qui possède ces données ; ici on ne fait que
        # les poser devant Sage. Absents → dits absents, jamais inventés.
        "cycle": cycle or "- inconnu (ni phase déclarée, ni détecteur)",
        "hier": hier or "rien (premier jour de carnet)",
    }


_LABEL_PHASE = {"recovery": "Reprise", "expansion": "Expansion",
                "slowdown": "Fin de cycle", "recession": "Récession"}


def _pct(v: Any) -> str:
    return f"{float(v):.0f} %"


def bloc_cycle(detecteur: Optional[dict], lecture: Optional[dict]) -> Optional[str]:
    """Le bloc « cycle » du prompt, depuis les deux réponses de l'API Pixel Office :
    `GET /api/alphabrief/cycle` (détecteur de prix) et `…/cycle/lecture` (phase
    déclarée × exposition, croisée par `lib/alphabrief_cycle.js` — on ne porte
    pas ce calcul en Python, on le lit). Chaque morceau absent est dit absent,
    jamais inventé. None si on ne sait rien du tout.

    Le libellé de `slowdown` est celui de la grille (« Fin de cycle »), pas
    celui du détecteur (« Ralentissement ») : une seule langue devant Sage."""
    from core.bitcoin.cycle_detector import WEIGHTS
    from core.cycle import mapping

    if lecture and lecture.get("pending"):
        lecture = None
    phase = (lecture or {}).get("phase") or None
    det_key = (detecteur or {}).get("phase")
    if not phase and not det_key:
        return None

    lignes = []
    if phase:
        date = str(phase.get("declared_at") or "")[:10]
        depuis = f" (depuis le {date[8:10]}/{date[5:7]})" if len(date) == 10 else ""
        lignes.append(f"- phase déclarée par Max : {_LABEL_PHASE.get(phase['key'], phase['key'])}{depuis}")
    else:
        lignes.append("- aucune phase déclarée par Max")

    if det_key:
        txt = f"- lecture du détecteur de prix : {_LABEL_PHASE.get(det_key, det_key)}"
        if detecteur.get("confidence") is not None:
            txt += f", confiance {int(detecteur['confidence'])} %"
        if detecteur.get("stale"):
            txt += " (relevé en retard)"
        if phase:
            txt += (" → en accord avec la phase déclarée" if phase["key"] == det_key
                    else " → en désaccord avec la phase déclarée")
        # Les deux indicateurs les plus lourds qui votent pour la lecture du
        # détecteur : ce qui la porte, pas la liste des onze.
        porteurs = sorted(
            (i for i in detecteur.get("indicators") or [] if i.get("vote") == det_key),
            key=lambda i: -WEIGHTS.get(i.get("key"), 0),
        )[:2]
        if porteurs:
            txt += " — porté par " + ", ".join(f"{i['name']} {i['signal']}" for i in porteurs)
        lignes.append(txt)
    else:
        lignes.append("- détecteur de prix indisponible")

    if phase:
        leaders = mapping.LEADERS.get(phase["key"], ())
        txt = "- secteurs en tête dans cette phase : " + ", ".join(mapping.SECTORS[s] for s in leaders)
        if phase.get("faible_discrimination"):
            txt += " (peu informatif en Expansion)"
        lignes.append(txt)

    expo = (lecture or {}).get("exposition") or {}
    if expo.get("total_positions"):
        parts = []
        if phase and expo.get("en_tete_pct") is not None:
            parts.append(f"{_pct(expo['en_tete_pct'])} en tête")
        if expo.get("cyclique_pct") is not None and expo.get("defensif_pct") is not None:
            parts.append(f"{_pct(expo['cyclique_pct'])} cyclique / {_pct(expo['defensif_pct'])} défensif")
        if parts:
            lignes.append("- tes actions : " + " · ".join(parts))

    return "\n".join(lignes)


def generate_daily_advice(
    agent_pref: Dict[str, Any], cycle: Optional[str] = None, hier: Optional[str] = None,
    phase_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Message du matin de Sage : au plus une idée à l'achat, au plus une à la
    vente, ou rien à faire — sur les lignes réelles de Max.

    Ne dépend plus de /api/patrimoine : les montants viennent des cotations
    live, ligne par ligne. L'API Pixel Office peut être à l'arrêt, le message
    du matin part quand même.

    Retourne None si la clé, le portefeuille ou la génération manquent — dans ce
    cas l'appelant n'envoie RIEN plutôt qu'un message vide ou faux. Sinon
    {"text", "achat", "vente", "raison"} : le texte à envoyer (sans la ligne de
    verdict) et le verdict structuré, chaque champ None s'il manque.

    `cycle` et `hier` : phrases déjà formatées (phase du cycle, dernier conseil
    du carnet) — Sage relit ce qu'il a dit la veille pour ne pas se répéter
    ni se contredire en silence.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set — Sage advice skipped")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — Sage advice skipped")
        return None

    ctx = _contexte(agent_pref, cycle=cycle, hier=hier, phase_key=phase_key)
    if not ctx:
        logger.warning("Sage: portefeuille illisible, message du jour annulé")
        return None

    prompt = _USER_TEMPLATE.format(
        total_eur=_fmt_eur(ctx["total_eur"]),
        cash_eur=_fmt_eur(ctx["cash_eur"]),
        risk=ctx["risk"],
        lignes=ctx["lignes"],
        candidats=ctx["candidats"],
        cycle=ctx["cycle"],
        hier=ctx["hier"],
    )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=25.0,
        )
        response = client.chat.completions.create(
            model="anthropic/claude-sonnet-5",
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=MAX_TOKENS,
            # `max_tokens` couvre le raisonnement AVANT le texte. Avec l'ancien
            # budget de 300, le modèle dépensait les 300 en raisonnement et
            # rendait un contenu vide (finish_reason "length", 300 reasoning
            # tokens, 0 mot) : Sage se taisait certains matins sans que rien ne
            # dise pourquoi. Un message de quatre lignes sur des chiffres déjà
            # triés n'a rien à délibérer — on coupe le raisonnement et on garde
            # un budget large. Champ propre à OpenRouter, comme la base_url.
            extra_body={"reasoning": {"enabled": False}},
        )
        choix = response.choices[0]
        text = (choix.message.content or "").strip()
        if not text:
            # Ne jamais retomber en silence : sans cette ligne, une réponse vide
            # et une panne réseau laissaient exactement la même trace.
            logger.warning(
                f"Sage: réponse vide du modèle (finish_reason={choix.finish_reason})"
            )
            return None
        text, verdict = _extraire_verdict(text)
        if not text:
            # Le modèle n'a rendu que la ligne JSON : rien à dire à Max.
            logger.warning("Sage: message vide une fois le verdict retiré")
            return None
        return {"text": text, **(verdict or {"achat": None, "vente": None, "raison": None})}
    except Exception as e:
        logger.error(f"Sage advice generation error: {e}")
        return None
