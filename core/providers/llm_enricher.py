"""Enrichissement qualitatif d'une carte : une phrase, les avantages
concurrentiels, ce qui pourrait faire bouger le titre.

Histoire (2026-09-18) : ce module visait DeepSeek avec une clé
`DEEPSEEK_API_KEY` qui n'a JAMAIS existé sur le VPS. `enrich_with_llm` rendait
`None` en silence (log en `debug`), si bien que 0 fiche sur 40 n'a jamais eu
de résumé et que `catalysts`/`key_risks` sont restés vides sur toutes les
cartes — pendant des mois, sans qu'aucune alerte ne le dise. Rebranché sur
OpenRouter avec le MÊME client que Sage (`sage_advisor.py`) : une seule façon
d'appeler un modèle dans ce repo, une seule clé, déjà présente.

Le modèle est Haiku 4.5 : la sortie est courte et factuelle, et l'appel tourne
pour toute la watchlist chaque matin (cache 48 h par ticker dans
`utils/cache.py`, section `llm`). Sortie EN FRANÇAIS — c'est la langue de la
fiche. `segments` et `top_competitors` ont été retirés du contrat : jamais
affichés, jamais persistés.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODEL = "anthropic/claude-haiku-4.5"
MAX_ITEMS = 3

_SYSTEM_PROMPT = (
    "Tu es un analyste actions senior. À partir de données financières structurées, "
    "tu produis une analyse qualitative courte et factuelle, en français. "
    "Réponds UNIQUEMENT par un JSON valide — pas de markdown, rien en dehors du JSON."
)

_USER_TEMPLATE = """\
Société : {name} ({ticker})
Secteur : {sector} | Industrie : {industry}
Capitalisation : {market_cap}

Chiffres clés :
- CAGR du CA 3 ans : {revenue_cagr_3y}%
- Marge EBIT : {ebit_margin}%
- Marge brute : {gross_margin}%
- Marge FCF : {fcf_margin}%
- Dette nette / EBITDA : {net_debt_ebitda}x
- Croissance du BPA : {eps_growth}%

Valorisation :
- P/E TTM : {pe_ttm}
- EV/EBITDA : {ev_ebitda}
- Rendement FCF : {fcf_yield}%

Momentum 12 mois vs marché : {rel_momentum_12m}%

Réponds avec exactement cette structure JSON :
{{
  "business_snapshot": {{
    "one_liner": "<une phrase : ce que fait la société et sa position sur son marché>",
    "moat_tags": ["<tag 1>", "<tag 2>"]
  }},
  "events": {{
    "catalysts": ["<catalyseur 1>", "<catalyseur 2>", "<catalyseur 3>"],
    "key_risks": ["<risque 1>", "<risque 2>", "<risque 3>"]
  }}
}}

Règles :
- one_liner : 25 mots max, factuel, ton neutre, en français
- moat_tags : 2 à 4 tags courts en français (ex. "Effets de réseau", "Pouvoir de prix", "Coûts de changement")
- catalysts et key_risks : 3 max chacun, une ligne chacun, SPÉCIFIQUES à la situation actuelle de cette société — jamais de généralité ("volatilité des marchés", "concurrence")
- null pour tout champ que tu ne peux pas déterminer avec confiance
"""


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _liste(valeurs: Any, maximum: int = MAX_ITEMS) -> List[str]:
    """Liste de chaînes non vides, tronquée. Tout le reste → []."""
    if not isinstance(valeurs, list):
        return []
    out = [str(v).strip() for v in valeurs if isinstance(v, (str, int, float)) and str(v).strip()]
    return out[:maximum]


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    """JSON du modèle → structure validée. None si la forme n'y est pas :
    on préfère une fiche sans IA à une fiche avec un texte de travers, et
    surtout on ne met PAS en cache 48 h une sortie inutilisable."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"LLM : JSON invalide ({e}) — {raw[:120]!r}")
        return None
    if not isinstance(data, dict):
        return None
    snap = data.get("business_snapshot") or {}
    events = data.get("events") or {}
    one_liner = snap.get("one_liner")
    out = {
        "business_snapshot": {
            "one_liner": one_liner.strip() if isinstance(one_liner, str) and one_liner.strip() else None,
            "moat_tags": _liste(snap.get("moat_tags"), 4),
        },
        "events": {
            "catalysts": _liste(events.get("catalysts")),
            "key_risks": _liste(events.get("key_risks")),
        },
    }
    if not out["business_snapshot"]["one_liner"] and not out["events"]["catalysts"] and not out["events"]["key_risks"]:
        logger.error("LLM : réponse sans contenu exploitable")
        return None
    return out


def enrich_with_llm(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Remplit business_snapshot (one_liner, moat_tags) et events (catalysts,
    key_risks). None si pas de clé, pas de client, ou sortie inexploitable —
    le scoring continue sans."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        # WARNING, pas debug : c'est ce silence qui a caché pendant des mois que
        # la couche IA ne tournait pas.
        logger.warning("OPENROUTER_API_KEY absente — fiche sans analyse IA")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("paquet openai absent — fiche sans analyse IA")
        return None

    ident = card.get("identity", {})
    fin = card.get("financials", {})
    val = card.get("valuation", {})
    market = card.get("market", {})

    prompt = _USER_TEMPLATE.format(
        name=ident.get("name") or ident.get("ticker", ""),
        ticker=ident.get("ticker", ""),
        sector=ident.get("sector") or "N/A",
        industry=ident.get("industry") or "N/A",
        market_cap=_fmt(ident.get("market_cap")),
        revenue_cagr_3y=_fmt(fin.get("revenue_cagr_3y")),
        ebit_margin=_fmt(fin.get("ebit_margin")),
        gross_margin=_fmt(fin.get("gross_margin")),
        fcf_margin=_fmt(fin.get("fcf_margin")),
        net_debt_ebitda=_fmt(fin.get("net_debt_to_ebitda")),
        eps_growth=_fmt(fin.get("eps_growth")),
        pe_ttm=_fmt(val.get("pe_ttm")),
        ev_ebitda=_fmt(val.get("ev_ebitda_ttm")),
        fcf_yield=_fmt(val.get("fcf_yield_ttm")),
        rel_momentum_12m=_fmt(market.get("relative_momentum_12m")),
    )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=25.0,
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=600,
            # Même précaution que Sage : sans ça, un modèle qui raisonne peut
            # dépenser le budget avant d'écrire le JSON (finish_reason "length").
            extra_body={"reasoning": {"enabled": False}},
        )
        raw = response.choices[0].message.content or ""
        return _parse(raw)
    except Exception as e:
        logger.error(f"LLM : appel échoué — {e}")
        return None
