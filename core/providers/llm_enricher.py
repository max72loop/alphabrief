from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior equity research analyst. "
    "Given structured financial data about a company, you produce a concise qualitative analysis. "
    "Always respond with valid JSON only — no markdown, no explanation outside the JSON."
)

_USER_TEMPLATE = """\
Company: {name} ({ticker})
Sector: {sector} | Industry: {industry}
Market cap: {market_cap}

Key financials:
- Revenue CAGR 3Y: {revenue_cagr_3y}%
- EBIT margin: {ebit_margin}%
- Gross margin: {gross_margin}%
- FCF margin: {fcf_margin}%
- Net debt / EBITDA: {net_debt_ebitda}x
- EPS growth: {eps_growth}%

Valuation:
- P/E TTM: {pe_ttm}
- EV/EBITDA: {ev_ebitda}
- FCF yield: {fcf_yield}%

Momentum 12M vs market: {rel_momentum_12m}%

Respond with this exact JSON structure:
{{
  "business_snapshot": {{
    "one_liner": "<one sentence describing what the company does and its market position>",
    "moat_tags": ["<tag1>", "<tag2>"],
    "segments": ["<main business segment>"],
    "top_competitors": ["<competitor1>", "<competitor2>"]
  }},
  "events": {{
    "catalysts": ["<catalyst 1>", "<catalyst 2>", "<catalyst 3>"],
    "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"]
  }}
}}

Rules:
- one_liner: max 25 words, factual, neutral tone
- moat_tags: 2-4 short tags (e.g. "Network effects", "Pricing power", "Switching costs")
- catalysts and key_risks: max 3 each, specific to this company's current situation
- Use null for any field you cannot determine confidently
"""


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def enrich_with_llm(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Calls DeepSeek to fill business_snapshot and events fields.
    Returns None if no API key configured or on failure.
    """
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        logger.debug("DEEPSEEK_API_KEY not set — skipping LLM enrichment")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — skipping LLM enrichment")
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
            base_url="https://api.deepseek.com",
            timeout=25.0,
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        raw = response.choices[0].message.content or ""
        # Strip potential markdown code fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM enrichment error: {e}")
        return None
