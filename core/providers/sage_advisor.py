from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Jamais de vocabulaire réglementé (« conseil en investissement », recommandation
# d'achat/vente formelle) — règle héritée de prompt_agent.txt (ère SaaS), toujours
# valable : conformité réglementaire française sur le conseil en investissement.
_SYSTEM_PROMPT = (
    "Tu es Sage, la voix personnelle qui commente le patrimoine de Max chaque matin. "
    "Tu n'es PAS un conseiller en investissement et tu ne dois JAMAIS employer ce "
    "vocabulaire réglementé, ni formuler de recommandation d'achat/vente formelle. "
    "Tu observes, tu contextualises, tu poses une question ou une remarque utile — "
    "jamais un ordre. Ton personnel, direct, en français. "
    "Réponds uniquement avec le message final, sans préambule ni guillemets, "
    "3 à 4 lignes maximum."
)

_USER_TEMPLATE = """\
Patrimoine total : {total_eur} € ({variation})
Répartition : {repartition}
Tolérance au risque affichée par Max (1=prudent, 5=agressif) : {risk}/5

Écris le message du jour pour Max. Adapte le ton à sa tolérance au risque :
prudent et rassurant si risk bas, plus direct/incisif si risk haut. Ne répète
pas les chiffres bruts mot pour mot, commente-les.
"""


def _fmt_eur(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _fmt_variation(value: Any) -> str:
    if value is None:
        return "variation inconnue"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "variation inconnue"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:,.0f} € vs dernière saisie".replace(",", " ")


def _fmt_repartition(items: Any) -> str:
    if not items:
        return "N/A"
    parts = []
    for r in items:
        classe = r.get("classe", "?")
        valeur = r.get("valeur_eur")
        parts.append(f"{classe}: {_fmt_eur(valeur)} €")
    return ", ".join(parts) if parts else "N/A"


def generate_daily_advice(patrimoine: Dict[str, Any], agent_pref: Dict[str, Any]) -> Optional[str]:
    """
    Génère le message quotidien de Sage (3-4 lignes, FR) à partir du payload
    de /api/patrimoine et de la préférence agent (/api/alphabrief/agent).

    Retourne None si la clé est absente ou l'appel échoue — l'appelant ne doit
    alors RIEN envoyer plutôt qu'un message vide ou une erreur brute à Max.
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

    prompt = _USER_TEMPLATE.format(
        total_eur=_fmt_eur(patrimoine.get("total_eur")),
        variation=_fmt_variation(patrimoine.get("variation_eur")),
        repartition=_fmt_repartition(patrimoine.get("repartition")),
        risk=agent_pref.get("risk", 3),
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
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=300,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:
        logger.error(f"Sage advice generation error: {e}")
        return None
