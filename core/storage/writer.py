"""
Writer AlphaBrief — Postgres local.
UPSERT dans ticker_scores, INSERT dans score_history.

Remplace core/storage/supabase_writer.py (client Supabase via HTTP). La
logique métier est inchangée ; seule la persistance a changé de nature.

`write_alert()` n'est pas repris : la fonction n'avait aucun appelant dans tout
le dépôt (vérifié par grep) et écrivait dans une table `alerts` qui n'a jamais
existé côté base. Elle échouait donc silencieusement à chaque appel qui n'a
jamais eu lieu. La fonctionnalité d'alertes se tranche au lot 4 — la recréer
ici reviendrait à réimplémenter du code mort.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict

from psycopg.types.json import Jsonb

from core.cycle import secteurs
from core.lynch import store as lynch
from core.storage import db

logger = logging.getLogger(__name__)


_colonnes: Dict[tuple, bool] = {}


def _a_colonne(table: str, colonne: str) -> bool:
    """La colonne existe-t-elle sur la base visée ? Lu une fois par process."""
    cle = (table, colonne)
    if cle not in _colonnes:
        try:
            _colonnes[cle] = db.query_one(
                "SELECT 1 AS ok FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                (table, colonne),
            ) is not None
        except Exception:
            _colonnes[cle] = False
    return _colonnes[cle]


def write_score(ticker: str, card: Dict[str, Any]) -> bool:
    """
    Upsert le score dans ticker_scores et insert dans score_history.
    Retourne True si succès, False sinon.
    """
    scores = card.get("scores", {})
    potential = scores.get("potential_score")
    confidence = scores.get("confidence_score")
    # Sous-scores 50/25/25 calculés par compute_potential_score. Fallback sur le
    # total pour les anciennes cards sérialisées avant l'introduction du breakdown
    # (évite d'écrire des null qui casseraient le front). Nommés _sc pour ne pas
    # entrer en collision avec `technicals` (dict) et `financials` (dict) plus bas.
    fundamentals_sc = scores.get("fundamentals_score")
    technicals_sc = scores.get("technicals_score")
    momentum_sc = scores.get("momentum_score")
    if fundamentals_sc is None:
        fundamentals_sc = potential
    if technicals_sc is None:
        technicals_sc = potential
    if momentum_sc is None:
        momentum_sc = potential

    # Détail du bloc fondamentaux. Contrairement aux trois sous-scores ci-dessus,
    # PAS de repli sur le total : une carte d'avant les piliers n'en a aucun, et
    # inventer cinq valeurs égales au total serait une explication fausse. NULL
    # dit « on ne sait pas », ce qui est exact.
    pillars_payload = None
    if scores.get("pillars"):
        pillars_payload = Jsonb({
            "pillars": scores.get("pillars"),
            "weights": scores.get("pillar_weights") or {},
            "convergence": scores.get("fundamentals_convergence"),
        })

    if potential is None:
        logger.warning(f"skip {ticker}: no potential_score")
        return False

    now = datetime.now(timezone.utc)
    identity = card.get("identity", {})
    market = card.get("market", {})
    financials = card.get("financials", {})
    valuation = card.get("valuation", {})
    technicals = card.get("technicals", {})
    business = card.get("business_snapshot", {})
    importance = scores.get("importance_ranked_items", [])

    # Merge financials + valuation into one dict for the financials JSONB column
    fin_merged = {}
    fin_merged.update(financials)
    fin_merged.update(valuation)

    market_data = {
        "beta": market.get("beta"),
        "rsi_14": technicals.get("rsi_14"),
        "sma_50": technicals.get("sma_50"),
        "sma_200": technicals.get("sma_200"),
        "momentum_3m": market.get("momentum_3m"),
        "momentum_12m": market.get("momentum_12m"),
        "analyst_target_mean": market.get("analyst_target_mean"),
        "analyst_recommendation": market.get("analyst_recommendation"),
    }

    row: Dict[str, Any] = {
        "ticker": ticker.upper(),
        "score_total": potential,
        "score_fundamentals": fundamentals_sc,
        "score_technicals": technicals_sc,
        "score_momentum": momentum_sc,
        "score_date": date.today(),
        "computed_at": now,
        "market_cap": identity.get("market_cap"),
        "one_liner": business.get("one_liner", ""),
        "moat_tags": Jsonb(business.get("moat_tags", [])),
        "score_label": scores.get("score_label", ""),
        # La bande et la confiance voyagent avec la note : l'API ne redérive
        # plus de verdict depuis le seul nombre. Voir db/schema.sql.
        "score_band": scores.get("score_band", ""),
        "confidence": confidence or 0,
        "importance_items": Jsonb(importance),
        "financials": Jsonb(fin_merged),
        "market_data": Jsonb(market_data),
    }
    # Champs d'identité : on ne les inclut que si FMP a effectivement renvoyé
    # une valeur. Sinon l'upsert écraserait des données déjà correctes
    # (ex. un backfill yfinance) avec des chaînes vides quand FMP est en
    # quota ou que /profile n'a rien renvoyé pour ce ticker.
    for col, key in (("company_name", "name"), ("sector", "sector"),
                     ("exchange", "exchange"), ("currency", "currency")):
        val = identity.get(key)
        if val:
            row[col] = val

    # Même précaution que ci-dessus : hors de l'upsert quand on n'a rien, sinon
    # un scoring dégradé effacerait le détail écrit par le précédent.
    if pillars_payload is not None:
        row["pillars"] = pillars_payload

    # « À surveiller » (catalyseurs / risques, llm_enricher). Un run sans IA
    # (clé absente, sortie invalide) ne doit pas effacer ce que le précédent
    # avait écrit — même règle que l'identité et les piliers.
    events = card.get("events", {}) or {}
    for col in ("catalysts", "key_risks"):
        val = events.get(col)
        if isinstance(val, list) and val:
            row[col] = Jsonb(val)

    # Prime de rendement + dilution par an (2026-10-27, migration
    # 2026_10_27_rendement.sql). Écrite seulement si la colonne existe : tant que
    # la migration n'est pas passée sur une base, le scoring y tourne comme avant.
    rendement = card.get("rendement") or {}
    if rendement and _a_colonne("ticker_scores", "rendement"):
        row["rendement"] = Jsonb({**rendement, "dilution": card.get("dilution") or {}})

    try:
        cols = list(row.keys())
        collist = ", ".join(cols)
        marks = ", ".join(["%s"] * len(cols))
        # Les colonnes absentes de l'upsert gardent leur valeur : c'est ce qui
        # protège un backfill yfinance quand FMP ne renvoie rien.
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "ticker")
        db.execute(
            f"INSERT INTO ticker_scores ({collist}) VALUES ({marks}) "
            f"ON CONFLICT (ticker) DO UPDATE SET {updates}",
            list(row.values()),
        )
        logger.info(f"upsert ticker_scores: {ticker} = {potential}/100")
    except Exception as e:
        logger.error(f"upsert ticker_scores failed for {ticker}: {e}")
        return False

    try:
        # La colonne est `scored_at`, pas `recorded_at`. L'ancienne migration
        # déclarait `recorded_at` et se trompait : la table déployée utilisait
        # `scored_at`, ce que lisait déjà le frontend. Chaque insert échouait
        # en PGRST204 depuis toujours, avalé par le except ci-dessous.
        # Le prix et les trois sous-scores partent AVEC la note : c'est ce qui
        # rend la calibration possible. `ticker_scores` porte bien les
        # sous-scores, mais écrasés à chaque scoring — l'historique, lui, ne
        # gardait qu'un total sans rien pour l'expliquer.
        db.execute(
            "INSERT INTO score_history "
            "(ticker, score, confidence, scored_at, price,"
            " score_fundamentals, score_technicals, score_momentum, pillars) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                ticker.upper(),
                potential,
                confidence or 0,
                now,
                market.get("current_price"),
                fundamentals_sc,
                technicals_sc,
                momentum_sc,
                pillars_payload,
            ],
        )
        logger.info(f"insert score_history: {ticker}")
    except Exception as e:
        # On continue — l'historique est secondaire face au score courant —
        # mais en ERROR, pas en WARNING : un historique qui ne s'écrit plus
        # ne doit pas se remarquer six mois plus tard sur un graphe plat.
        logger.error(f"insert score_history ECHEC pour {ticker}: {e}")

    # Secteur GICS de la société (couche « phase de cycle »). Posé une fois,
    # jamais écrasé — voir core/cycle/secteurs.py. Même politique d'erreur que
    # l'historique : ERROR et on continue, le score est l'essentiel.
    try:
        secteurs.enregistrer(ticker, card)
    except Exception as e:
        logger.error(f"societes.secteur_gics ECHEC pour {ticker}: {e}")

    # Catégorie de Peter Lynch — grille de lecture, recalculée à chaque scoring
    # sauf correction de Max (voir core/lynch/store.py). Même politique d'erreur.
    try:
        lynch.enregistrer_fiche(ticker, fin_merged, nom=(card.get("identity") or {}).get("name"))
    except Exception as e:
        logger.error(f"societes.lynch_categorie ECHEC pour {ticker}: {e}")

    return True
