from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.providers.price_identity import fetch_identity_and_market
from core.features.momentum import compute_momentum_12m, compute_relative_momentum
from core.features.technicals import compute_technicals
from core.scoring.potential import compute_potential_score, benefice_exceptionnel, est_banque_ou_assurance, to_float
from core.scoring.prime import calculer_prime
from core.scoring.dilution import calculer_dilution
from core.providers.rendement import fetch_rendement, taux_10y
from core.scoring.secteur import secteur_manuel, secteur_moteur
from core.providers.fundamentals_yf import fetch_core_fundamentals
from core.providers.llm_enricher import enrich_with_llm
from core.scoring.importance import build_importance_items
from core.scoring.confidence import compute_confidence_score
from core.scoring import bands
from utils import cache as _cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _score_label(score: Optional[int]) -> str:
    """Délègue au barème unique (core.scoring.bands).

    Les seuils vivaient ici en dur (80/65/50/35/20) et contredisaient les trois
    autres barèmes du système — dont deux étaient inatteignables : le moteur n'a
    jamais produit plus de 68 en neuf mois. Voir core/scoring/bands.py.
    """
    return bands.score_label(score)


def empty_card(ticker: str) -> Dict[str, Any]:
    return {
        "as_of": date.today().isoformat(),
        "identity": {
            "ticker": ticker.upper(),
            "name": "",
            "exchange": "",
            "currency": "",
            "sector": "",
            "industry": "",
            "market_cap": None,
        },
        "business_snapshot": {
            "one_liner": "",
            "segments": [],
            "geographies": [],
            "moat_tags": [],
            "top_competitors": [],
        },
        "financials": {
            "revenue_cagr_3y": None,
            "revenue_yoy_rates": None,
            "ebit_margin": None,
            "gross_margin": None,
            "fcf_margin": None,
            "roe": None,
            "roa": None,
            "net_debt_to_ebitda": None,
            "interest_coverage": None,
            "share_dilution_3y": None,
            "dilution_an": None,     # %/an retenu pour la note (core/scoring/dilution.py)
            "payout_ratio": None,
            "fcf_absolute": None,
            "net_income": None,
            "current_ratio": None,
            "eps_growth": None,
            "net_margin": None,
            "insider_ownership": None,
            "short_interest": None,
            "gross_margin_trend": None,
            "accruals_ratio": None,
            "institutional_ownership": None,
            "altman_z": None,
        },
        "valuation": {
            "pe_ttm": None,
            "ev_ebitda_ttm": None,
            "ev_sales_ttm": None,
            "fcf_yield_ttm": None,
            "pb_ratio": None,
            "price_to_ocf": None,
        },
        "market": {
            "beta": None,
            # FIX M3 (audit 2026-05-13) : champs alignés avec fetch_identity_and_market.
            # `volatility_1y` et `drawdown_1y` retirés d'ici (gardés uniquement dans
            # technicals où ils sont calculés).
            "avg_volume_3m": None,
            "current_price": None,
            "previous_close": None,
            "change_pct": None,
            "volume": None,
            "fifty_two_week_low": None,
            "fifty_two_week_high": None,
            "dividend_yield": None,
            "momentum_1m": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "relative_momentum_1m": None,
            "relative_momentum_3m": None,
            "relative_momentum_12m": None,
            "analyst_target_mean": None,
            "analyst_target_low": None,
            "analyst_target_high": None,
            "analyst_count": None,
            "analyst_recommendation": None,
        },
        "technicals": {
            "rsi_14": None,
            "sma_50": None,
            "sma_200": None,
            "macd_line": None,
            "macd_signal": None,
            "macd_histogram": None,
            "volatility_1y": None,
            "max_drawdown_1y": None,
        },
        "events": {
            "next_earnings_date": None,
            "catalysts": [],
            "key_risks": [],
        },
        # Prime de rendement (core/scoring/prime.py) et dilution par an
        # (core/scoring/dilution.py), posées par generate_card. Vides = non calculées.
        "rendement": {},
        "dilution": {},
        "scores": {
            "potential_score": None,
            "fundamentals_score": None,
            "technicals_score": None,
            "momentum_score": None,
            "pillars": {},
            "pillar_weights": {},
            "fundamentals_convergence": None,
            "score_label": None,
            "importance_ranked_items": [],
            "confidence_score": None,
        },
        "sources": [
            {
                "name": "stub",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


def generate_card(ticker: str, progress_callback=None) -> Dict[str, Any]:
    card = empty_card(ticker)
    _cb = progress_callback or (lambda msg: None)

    _cb("Récupération des données en cours...")

    def _fetch_identity():
        cached = _cache.load(ticker, "identity")
        if cached:
            return cached
        data = fetch_identity_and_market(ticker)
        _cache.save(ticker, "identity", data)
        return data

    def _fetch_momentum():
        cached = _cache.load(ticker, "momentum")
        if cached:
            return cached
        data = compute_momentum_12m(ticker)
        if data:
            _cache.save(ticker, "momentum", data)
        return data

    def _has_useful_fundamentals(payload):
        if not payload:
            return False
        fin = payload.get("financials", {})
        val = payload.get("valuation", {})
        return sum(1 for v in {**fin, **val}.values() if v is not None) >= 3

    def _fetch_fundamentals():
        cached = _cache.load(ticker, "fundamentals")
        if _has_useful_fundamentals(cached):
            return cached
        data = fetch_core_fundamentals(ticker)
        if _has_useful_fundamentals(data):
            _cache.save(ticker, "fundamentals", data)
        return data

    def _fetch_technicals():
        cached = _cache.load(ticker, "technicals")
        if cached:
            return cached
        data = compute_technicals(ticker)
        _cache.save(ticker, "technicals", data)
        return data

    with ThreadPoolExecutor() as executor:
        future_id = executor.submit(_fetch_identity)
        future_mom = executor.submit(_fetch_momentum)
        future_fund = executor.submit(_fetch_fundamentals)
        future_tech = executor.submit(_fetch_technicals)

        # identity + market
        try:
            data = future_id.result()
            card["identity"].update(
                {k: v for k, v in data["identity"].items() if v is not None}
            )
            card["market"].update(
                {k: v for k, v in data["market"].items() if v is not None}
            )
            card["sources"].append(
                {
                    "name": data.get("source", "yfinance"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _cb("✓ Identité & données de marché")
        except Exception as e:
            logger.error(f"Error fetching identity/market for {ticker}: {e}")
            _cb("⚠ Identité & données de marché (erreur)")

        # momentum
        try:
            mom = future_mom.result()
            if mom is not None:
                card["market"].update({k: v for k, v in mom.items() if v is not None})
            _cb("✓ Momentum calculé")
        except Exception as e:
            logger.error(f"Error computing momentum for {ticker}: {e}")
            _cb("⚠ Momentum (erreur)")

        # fundamentals
        try:
            f = future_fund.result()
            card["financials"].update(
                {k: v for k, v in f["financials"].items() if v is not None}
            )
            card["valuation"].update(
                {k: v for k, v in f["valuation"].items() if v is not None}
            )
            _cb("✓ Fondamentaux récupérés")
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker}: {e}")
            _cb("⚠ Fondamentaux (erreur)")

        # technicals
        try:
            tech = future_tech.result()
            card["technicals"].update(
                {k: v for k, v in tech.items() if v is not None}
            )
            _cb("✓ Indicateurs techniques")
        except Exception as e:
            logger.error(f"Error computing technicals for {ticker}: {e}")
            _cb("⚠ Indicateurs techniques (erreur)")

    # Momentum relatif au secteur (post-executor : requiert le secteur de l'identity)
    _cb("Momentum relatif au secteur...")
    # Le secteur de NOTATION (core/scoring/secteur.py) : correction manuelle de
    # Max d'abord, sinon yfinance traduit dans la langue des tables. `sector`
    # reste le libellé brut de la source ; `sector_note` est ce que le moteur lit.
    sector = secteur_moteur(card["identity"].get("sector"), secteur_manuel(ticker))
    card["identity"]["sector_note"] = sector
    try:
        rel_mom = compute_relative_momentum(ticker, sector)
        if rel_mom:
            card["market"].update({k: v for k, v in rel_mom.items() if v is not None})
    except Exception as e:
        logger.error(f"Error computing relative momentum for {ticker}: {e}")

    # Prime de rendement et dilution (2026-10-27). Une valorisation basse ne suffit
    # plus quand le 10 ans US paie ~5 % : on compare le rendement au taux sans
    # risque (core/scoring/prime.py) et on lit la dilution par an sur 1 et 3 ans
    # (core/scoring/dilution.py). La dilution entre dans la note (pilier Qualité) ;
    # la prime reste EN OMBRE — affichée et historisée, sans poids dans la note.
    _cb("Rendement contre le taux 10 ans...")
    try:
        devise = card["identity"].get("currency") or None
        rd = fetch_rendement(ticker, devise)
        dil = calculer_dilution(rd.get("actions_q") or [], card["financials"].get("share_dilution_3y"),
                                dates=rd.get("actions_dates"), ipo_date=rd.get("ipo_date"))
        dil["source"] = rd.get("actions_source") if dil.get("source") == "trimestriel" else dil.get("source")
        card["dilution"] = dil
        card["financials"]["dilution_an"] = dil["retenue"]

        fin, val = card["financials"], card["valuation"]
        pe_ttm = val.get("pe_ttm")
        if benefice_exceptionnel(to_float(pe_ttm), to_float(val.get("forward_pe")), to_float(fin.get("roe"))):
            pe_ttm = None   # même garde-fou que le pilier Valeur
        # FCF publié dans une autre devise que la cotation (TSM : FCF en TWD,
        # capitalisation en USD → « FCF yield » de 45 % au lieu de ~1,4 %). Le
        # yield de la prime est recalculé dans la devise de la capitalisation ;
        # sans cours de change, il reste inconnu plutôt que faux.
        # ⚠ `valuation.fcf_yield_ttm`, lu par le pilier Valeur, porte encore
        # l'erreur — correction à part, elle déplace des notes.
        fcf_yield = val.get("fcf_yield_ttm")
        pub = rd.get("devise_publication")
        conversion = None
        if pub and devise and pub.upper() != devise.upper():
            fx, fcf_abs, mcap = to_float(rd.get("fx_publication")), to_float(fin.get("fcf_absolute")), to_float(card["identity"].get("market_cap"))
            fcf_yield = (fcf_abs * fx / mcap * 100.0) if fx and fcf_abs is not None and mcap else None
            conversion = {"de": pub, "vers": devise, "fx": fx}
        taux = taux_10y() or {}
        card["rendement"] = calculer_prime(
            taux_10y=taux.get("taux"),
            fcf_yield=fcf_yield,
            fcf_ttm=fin.get("fcf_absolute"),
            forward_pe=val.get("forward_pe"),
            pe_ttm=pe_ttm,
            croissance_ca=rd.get("croissance_ca"),
            financiere=est_banque_ou_assurance(sector, card["identity"].get("industry")),
        )
        card["rendement"].update(
            taux_date=taux.get("date"), taux_source=taux.get("source"),
            croissance_source=rd.get("croissance_source"),
            conversion_fcf=conversion,
        )
    except Exception as e:
        logger.error(f"Rendement/dilution indisponibles pour {ticker}: {e}")

    # LLM enrichment (business snapshot + events)
    _cb("Analyse IA en cours...")
    try:
        cached_llm = _cache.load(ticker, "llm")
        if cached_llm:
            llm_data = cached_llm
            _cb("✓ Analyse IA (cache)")
        else:
            llm_data = enrich_with_llm(card)
            if llm_data:
                _cache.save(ticker, "llm", llm_data)
        if llm_data:
            card["business_snapshot"].update(
                {k: v for k, v in llm_data.get("business_snapshot", {}).items() if v is not None}
            )
            card["events"].update(
                {k: v for k, v in llm_data.get("events", {}).items() if v is not None}
            )
            _cb("✓ Analyse IA terminée")
        else:
            _cb("— Analyse IA indisponible")
    except Exception as e:
        logger.error(f"LLM enrichment failed for {ticker}: {e}")
        _cb("⚠ Analyse IA (erreur)")

    # scoring
    _cb("Calcul du score de potentiel...")
    breakdown = compute_potential_score(card)
    _cb("Analyse des facteurs clés...")
    card["scores"]["importance_ranked_items"] = build_importance_items(card, limit=10)

    _cb("Score de confiance...")
    confidence = compute_confidence_score(card)
    card["scores"]["confidence_score"] = confidence

    # La note est publiée telle que le moteur la calcule.
    #
    # Elle a longtemps été rabotée par `factor = 0.8 + 0.2*confiance/100`, la
    # confiance mesurant la DISPONIBILITÉ DES DONNÉES. Le nombre répondait donc
    # à deux questions à la fois — « cette société vaut-elle quelque chose » et
    # « qu'est-ce qu'on en sait » — sans que le lecteur puisse démêler les deux.
    # L'historique du rabot dit assez qu'il n'a jamais trouvé son réglage : le
    # plancher est passé de 0.5 à 0.8 (FIX I1) pour cesser de transformer un 50
    # neutre en « Faible », puis l'étiquette a dû être déplacée d'avant à après
    # le facteur (FIX I4) parce que la carte affichait le nombre d'après et le
    # mot d'avant.
    #
    # Il était en plus asymétrique — il ne pouvait que baisser, jamais relever —
    # et les bandes ne font que 4 à 6 points de large : au 2026-09-07 il
    # déplaçait 4 cartes sur 39 d'une bande entière (NU 61→58 et HOOD 62→59
    # perdaient « Exceptionnel », ASR 51→47 et 7974.T 51→49 « Modéré »).
    #
    # Le garde-fou n'a pas disparu, il a changé de place : il porte désormais
    # sur l'étiquette (core.scoring.bands.band_for), qui refuse de délivrer un
    # verdict sous le plancher de couverture. Un nombre, un sens.
    card["scores"]["potential_score"]    = int(round(breakdown["total"]))
    card["scores"]["fundamentals_score"] = int(round(breakdown["fundamentals"]))
    card["scores"]["technicals_score"]   = int(round(breakdown["technicals"]))
    card["scores"]["momentum_score"]     = int(round(breakdown["momentum"]))

    # Détail du bloc fondamentaux (Quality/Growth/Value/Risk/Analyst). Le moteur
    # le calculait déjà ; il ne le rendait pas, si bien qu'une note de 62 arrivait
    # à l'écran sans dire quel pilier la portait. Les poids voyagent avec les
    # valeurs : ils dépendent de la couverture analyste, donc les recopier en dur
    # côté écran les ferait mentir un jour sur deux.
    card["scores"]["pillars"]        = breakdown["pillars"]
    card["scores"]["pillar_weights"] = breakdown["pillar_weights"]
    card["scores"]["fundamentals_convergence"] = breakdown["fundamentals_convergence"]

    # Le libellé porte sur le score publié — qui est maintenant le seul qui
    # existe. C'était tout l'objet du FIX I4 (audit 2026-05-13) : tant que le
    # facteur de confiance existait, il y avait DEUX nombres (avant et après
    # rabot) et l'écran pouvait afficher le mot de l'un à côté du chiffre de
    # l'autre — « HOOD 59 · Exceptionnel » quand Exceptionnel commence à 60,
    # sept cartes sur trente-huit au 2026-09-03. Le facteur retiré, la
    # contradiction n'a plus de support possible.
    #
    # Reste à ne pas délivrer de verdict sur des données trouées : c'est
    # `band_for` qui s'en charge, en rendant la bande « Données insuffisantes »
    # sous le plancher de couverture. La confiance elle-même reste lisible telle
    # quelle dans `confidence_score`, à côté de la note et non plus dedans.
    _total = card["scores"]["potential_score"]
    # Bande complète (clé, rang, ton) à côté du libellé : les surfaces d'affichage
    # n'ont plus à redériver un verdict depuis le nombre — c'est exactement ce
    # qui avait fait diverger le front Vercel et Pixel Office du backend.
    _band = bands.band_for(_total, confidence)
    card["scores"]["score_label"] = _band["label"]
    card["scores"]["score_band"] = _band["key"]
    card["scores"]["score_percentile"] = _band["percentile"]
    _cb("Analyse terminée !")

    # Aucune écriture ici : generate_card calcule, il ne persiste pas.
    # L'appel à core.supabase_sink.upsert_ticker_score() qui vivait à cet
    # endroit lisait SUPABASE_SERVICE_ROLE_KEY, une variable qui n'a jamais
    # été définie sur le VPS — il était donc no-op depuis toujours, et le
    # retirer ne fait perdre aucune écriture. La persistance est faite par
    # l'appelant (daemon ou CLI) via core.storage.writer.write_score().
    return card


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", help="e.g. AAPL")
    parser.add_argument("--outdir", default="data/cards", help="output directory")
    args = parser.parse_args()

    card = generate_card(args.ticker)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / f"{args.ticker.upper()}.json"

    outpath.write_text(
        json.dumps(card, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {outpath}")


if __name__ == "__main__":
    main()
