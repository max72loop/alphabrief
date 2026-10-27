"""
Résultats trimestriels de MES sociétés (positions ouvertes) → table
`resultats_trimestriels` du Postgres local. Lue par Pixel Office, onglet
« Résultats » (/api/alphabrief/resultats).

Pour chaque société détenue, sous son ticker NOTÉ (listings.resolve) :
  · les publications passées : BPA attendu / publié, surprise, verdict, et le
    chiffre d'affaires du trimestre rattaché avec celui d'un an plus tôt ;
  · la prochaine publication : date (souvent estimée par yfinance), BPA et CA
    attendus, CA du même trimestre un an avant (→ croissance attendue) ;
  · une lecture IA de 2-3 phrases, écrite UNE fois par publication et gardée,
    rapprochée de la thèse de Max (societes.these) quand il y en a une.

Tout ce qui calcule est pur et testé (tests/core/providers/test_trimestres_yf.py) :
surprise, verdict, rattachement trimestre → publication, CA un an avant.
yfinance et la base ne sont touchés que par `sync_trimestres_for` et
`ecrire_lectures`.

Usage manuel :
    python -m core.providers.trimestres_yf            # synchro + lectures, sociétés détenues
    python -m core.providers.trimestres_yf GOOG TSM   # synchro seule de ces tickers
"""
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Une surprise de ±2 % sur le BPA est dans le bruit des arrondis et des
# ajustements : « conforme ». Au-delà, battu ou raté. Seul seuil du verdict —
# l'API et l'écran le lisent, ils ne le recalculent pas.
SEUIL_VERDICT_PCT = 2.0

# Un trimestre se publie dans les ~3 mois qui suivent sa clôture ; au-delà,
# le rattachement serait une devinette.
DELAI_PUBLICATION_MAX_J = 120
# « Même trimestre un an plus tôt » : 365 j ± une marge pour les exercices
# décalés (52/53 semaines).
ECART_UN_AN_J = (340, 390)

# Lecture IA : seulement sur une publication récente (inutile de commenter un
# trimestre d'il y a un an), et un plafond d'appels par passage.
LECTURE_FENETRE_J = 100
LECTURE_MAX_PAR_PASSAGE = 25
MODEL = "anthropic/claude-haiku-4.5"


# ── Calculs purs ─────────────────────────────────────────────

def _num(v: Any) -> Optional[float]:
    """float fini ou None (NaN, None, texte → None)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _montant(v: Any) -> Optional[float]:
    """Un chiffre d'affaires : strictement positif, sinon inconnu. yfinance rend
    0 pour le consensus d'un émetteur semestriel (RIO.AX) — ce n'est pas un CA."""
    f = _num(v)
    return f if f is not None and f > 0 else None


def surprise_pct(attendu: Any, publie: Any) -> Optional[float]:
    """(publié − attendu) / |attendu| × 100. None si l'un manque ou attendu = 0."""
    a, p = _num(attendu), _num(publie)
    if a is None or p is None or a == 0:
        return None
    return round((p - a) / abs(a) * 100, 2)


def verdict(surprise: Optional[float]) -> Optional[str]:
    """'battu' | 'conforme' | 'rate' selon SEUIL_VERDICT_PCT, None sans surprise."""
    if surprise is None:
        return None
    if surprise >= SEUIL_VERDICT_PCT:
        return "battu"
    if surprise <= -SEUIL_VERDICT_PCT:
        return "rate"
    return "conforme"


def rattacher(date_pub: date, fins: Iterable[date]) -> Optional[date]:
    """Le trimestre publié ce jour-là : la clôture la plus récente STRICTEMENT
    avant la publication, à moins de DELAI_PUBLICATION_MAX_J jours."""
    candidates = [f for f in fins if f < date_pub and (date_pub - f).days <= DELAI_PUBLICATION_MAX_J]
    return max(candidates) if candidates else None


def un_an_avant(fin: date, fins: Iterable[date]) -> Optional[date]:
    """La clôture du même trimestre un an plus tôt, s'il y en a une."""
    lo, hi = ECART_UN_AN_J
    candidates = [f for f in fins if lo <= (fin - f).days <= hi]
    return min(candidates, key=lambda f: abs((fin - f).days - 365)) if candidates else None


def construire_lignes(
    ticker: str,
    publications: list[dict],
    trimestres: dict[date, dict],
    prochain_ca: Optional[dict],
    devise: Optional[str],
    aujourd_hui: date,
) -> list[dict]:
    """Assemble les lignes à écrire.

    publications : [{date: date, bpa_attendu, bpa_publie}] (earnings_dates)
    trimestres   : {fin_trimestre: {ca, resultat_net}} (quarterly_income_stmt)
    prochain_ca  : {avg, year_ago} du consensus CA du prochain trimestre, ou None
    """
    fins = list(trimestres)
    lignes = []
    prochaine = min((p["date"] for p in publications if p["date"] >= aujourd_hui), default=None)
    for p in publications:
        d = p["date"]
        publie = _num(p.get("bpa_publie"))
        s = surprise_pct(p.get("bpa_attendu"), publie)
        fin = rattacher(d, fins) if publie is not None else None
        ca = trimestres.get(fin, {}).get("ca") if fin else None
        fin_1a = un_an_avant(fin, fins) if fin else None
        ligne = {
            "ticker": ticker,
            "date_publication": d,
            "fin_trimestre": fin,
            "bpa_attendu": _num(p.get("bpa_attendu")),
            "bpa_publie": publie,
            "surprise_pct": s,
            "verdict": verdict(s) if publie is not None else None,
            "ca": _montant(ca),
            "ca_attendu": None,
            "ca_un_an_avant": _montant(trimestres.get(fin_1a, {}).get("ca")) if fin_1a else None,
            "resultat_net": _num(trimestres.get(fin, {}).get("resultat_net")) if fin else None,
            "devise": devise,
        }
        # Le consensus CA de yfinance porte sur le PROCHAIN trimestre seulement.
        if d == prochaine and publie is None and prochain_ca:
            ligne["ca_attendu"] = _montant(prochain_ca.get("avg"))
            ligne["ca_un_an_avant"] = _montant(prochain_ca.get("year_ago"))
        lignes.append(ligne)
    return lignes


# ── yfinance ─────────────────────────────────────────────────

def _lire_yf(ticker: str) -> tuple[list[dict], dict[date, dict], Optional[dict], Optional[str]]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    publications: list[dict] = []
    try:
        df = t.earnings_dates
    except Exception as e:
        logger.debug(f"earnings_dates {ticker}: {e}")
        df = None
    if df is not None and len(df):
        for ts, row in df.iterrows():
            try:
                d = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            except Exception:
                continue
            publications.append({
                "date": d,
                "bpa_attendu": row.get("EPS Estimate"),
                "bpa_publie": row.get("Reported EPS"),
            })

    trimestres: dict[date, dict] = {}
    try:
        qi = t.quarterly_income_stmt
    except Exception as e:
        logger.debug(f"quarterly_income_stmt {ticker}: {e}")
        qi = None
    if qi is not None and len(qi.columns):
        for col in qi.columns:
            try:
                fin = col.date() if hasattr(col, "date") else date.fromisoformat(str(col)[:10])
            except Exception:
                continue
            ca = qi.at["Total Revenue", col] if "Total Revenue" in qi.index else None
            rn = qi.at["Net Income", col] if "Net Income" in qi.index else None
            trimestres[fin] = {"ca": _num(ca), "resultat_net": _num(rn)}

    prochain_ca = None
    try:
        re_ = t.revenue_estimate
        if re_ is not None and "0q" in re_.index:
            prochain_ca = {"avg": re_.at["0q", "avg"], "year_ago": re_.at["0q", "yearAgoRevenue"]}
    except Exception as e:
        logger.debug(f"revenue_estimate {ticker}: {e}")

    devise = None
    try:
        devise = (t.info or {}).get("financialCurrency")
    except Exception as e:
        logger.debug(f"info {ticker}: {e}")

    return publications, trimestres, prochain_ca, devise


# ── Base ─────────────────────────────────────────────────────

_COLONNES = (
    "ticker", "date_publication", "fin_trimestre", "bpa_attendu", "bpa_publie",
    "surprise_pct", "verdict", "ca", "ca_attendu", "ca_un_an_avant", "resultat_net", "devise",
)


_GARDES = ("fin_trimestre", "ca", "ca_un_an_avant", "resultat_net")


def _ecrire(ticker: str, lignes: list[dict], aujourd_hui: date) -> int:
    """Upsert sur (ticker, date_publication). Les lignes À VENIR du ticker sont
    d'abord retirées : une date estimée qui bouge ne doit pas laisser de
    fantôme. La lecture IA d'une publication passée n'est jamais touchée."""
    from core.storage import db

    cols = ", ".join(_COLONNES)
    vals = ", ".join(f"%({c})s" for c in _COLONNES)
    # yfinance ne garde que ~5 trimestres de compte de résultat : un CA déjà
    # connu ne doit pas redevenir NULL quand son trimestre sort de la fenêtre.
    maj = ", ".join(
        f"{c} = COALESCE(EXCLUDED.{c}, resultats_trimestriels.{c})" if c in _GARDES else f"{c} = EXCLUDED.{c}"
        for c in _COLONNES if c not in ("ticker", "date_publication")
    )
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM resultats_trimestriels "
                "WHERE ticker = %s AND bpa_publie IS NULL AND date_publication >= %s",
                (ticker, aujourd_hui),
            )
            cur.executemany(
                f"INSERT INTO resultats_trimestriels ({cols}) VALUES ({vals}) "
                f"ON CONFLICT (ticker, date_publication) DO UPDATE SET {maj}, updated_at = now()",
                lignes,
            )
            # CA d'un an avant tiré de la table elle-même : l'historique se
            # complète au fil des mois, au-delà des 5 trimestres de yfinance.
            cur.execute(
                "UPDATE resultats_trimestriels r SET ca_un_an_avant = p.ca "
                "  FROM resultats_trimestriels p "
                " WHERE r.ticker = %s AND p.ticker = r.ticker AND r.ca_un_an_avant IS NULL "
                "   AND r.fin_trimestre IS NOT NULL AND p.fin_trimestre IS NOT NULL AND p.ca IS NOT NULL "
                "   AND (r.fin_trimestre - p.fin_trimestre) BETWEEN %s AND %s",
                (ticker, *ECART_UN_AN_J),
            )
    return len(lignes)


def tickers_detenus() -> list[str]:
    """Actions des positions ouvertes, sous le symbole NOTÉ (GOOGL → GOOG)."""
    from core.scoring import listings
    from core.storage import db

    out = set()
    for row in db.query("SELECT actif FROM positions WHERE ouverte AND classe = 'actions'"):
        scored = listings.resolve(row["actif"])
        if scored:
            out.add(scored.upper())
    return sorted(out)


def sync_trimestres_for(ticker: str, aujourd_hui: Optional[date] = None) -> int:
    """Synchronise un ticker. Renvoie le nombre de lignes écrites (0 si rien)."""
    aujourd_hui = aujourd_hui or date.today()
    upper = ticker.upper()
    publications, trimestres, prochain_ca, devise = _lire_yf(upper)
    if not publications:
        return 0
    lignes = construire_lignes(upper, publications, trimestres, prochain_ca, devise, aujourd_hui)
    try:
        n = _ecrire(upper, lignes, aujourd_hui)
    except Exception as e:
        logger.warning(f"resultats_trimestriels {upper}: écriture échouée — {e}")
        return 0
    logger.info(f"  ↳ {upper}: {n} publication(s) trimestrielles")
    return n


# ── Lecture IA ───────────────────────────────────────────────

_SYSTEM = (
    "Tu es l'analyste personnel d'un investisseur particulier qui garde ses titres "
    "plusieurs années. On te donne les derniers résultats trimestriels d'une société "
    "qu'il détient. En 2 ou 3 phrases, en français, dis ce que ce trimestre change. "
    "Appuie-toi UNIQUEMENT sur les chiffres fournis, n'invente ni guidance ni "
    "contexte. Aucun conseil d'achat ou de vente, aucun objectif de cours. Si une "
    "thèse d'investissement est fournie, termine par une phrase qui dit si ces "
    "chiffres la confortent, la contredisent, ou n'en disent rien. Texte brut, "
    "400 caractères au plus."
)


def _fmt_ca(v: Optional[float], devise: Optional[str]) -> str:
    if v is None:
        return "n.d."
    return f"{v / 1e9:.2f} Md {devise or ''}".strip()


def prompt_lecture(nom: str, lignes: list[dict], these: Optional[str]) -> str:
    """Les 4 dernières publications, de la plus récente à la plus ancienne."""
    out = [f"Société : {nom}"]
    for l in lignes[:4]:
        s = l.get("surprise_pct")
        croiss = ""
        if l.get("ca") and l.get("ca_un_an_avant"):
            croiss = f", {(l['ca'] / l['ca_un_an_avant'] - 1) * 100:+.1f} % sur un an"
        out.append(
            f"- Publication du {l['date_publication']} : BPA {l.get('bpa_publie')} "
            f"contre {l.get('bpa_attendu')} attendu"
            + (f" (surprise {s:+.1f} %)" if s is not None else "")
            + f" ; CA {_fmt_ca(l.get('ca'), l.get('devise'))}{croiss}"
        )
    if these:
        out.append(f"Thèse de l'investisseur : « {these[:600]} »")
    return "\n".join(out)


def _appeler_llm(prompt: str) -> Optional[str]:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY absente — trimestres sans lecture IA")
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=25.0)
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
            extra_body={"reasoning": {"enabled": False}},
        )
        txt = (r.choices[0].message.content or "").strip()
        return txt[:600] or None
    except Exception as e:
        logger.error(f"lecture trimestre : appel LLM échoué — {e}")
        return None


def ecrire_lectures(tickers: Iterable[str], aujourd_hui: Optional[date] = None) -> int:
    """Pour chaque ticker : si sa dernière publication (récente) n'a pas de
    lecture, en écrire une. Renvoie le nombre de lectures écrites."""
    from core.storage import db

    aujourd_hui = aujourd_hui or date.today()
    depuis = aujourd_hui - timedelta(days=LECTURE_FENETRE_J)
    theses = {r["ticker"].upper(): r["these"].strip()
              for r in db.query("SELECT ticker, these FROM societes WHERE these IS NOT NULL AND these <> ''")}
    from core.scoring import listings

    noms = {}
    for r in db.query("SELECT actif, libelle FROM positions WHERE ouverte AND libelle IS NOT NULL"):
        noms[(listings.resolve(r["actif"]) or r["actif"]).upper()] = r["libelle"]

    ecrites = 0
    for t in tickers:
        if ecrites >= LECTURE_MAX_PAR_PASSAGE:
            break
        lignes = db.query(
            "SELECT * FROM resultats_trimestriels WHERE ticker = %s AND bpa_publie IS NOT NULL "
            "ORDER BY date_publication DESC LIMIT 4",
            (t,),
        )
        if not lignes:
            continue
        derniere = lignes[0]
        if derniere["lecture"] or derniere["date_publication"] < depuis:
            continue
        lignes = [{k: (float(v) if hasattr(v, "is_finite") else v) for k, v in l.items()} for l in lignes]
        txt = _appeler_llm(prompt_lecture(noms.get(t, t), lignes, theses.get(t)))
        if not txt:
            continue
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE resultats_trimestriels SET lecture = %s, lecture_at = now() WHERE id = %s",
                    (txt, derniere["id"]),
                )
        ecrites += 1
        logger.info(f"  ↳ {t}: lecture du trimestre écrite")
    return ecrites


def sync_detenus() -> dict:
    """Synchro + lectures pour toutes les sociétés détenues. Appelé par le daemon."""
    tickers = tickers_detenus()
    n = 0
    for t in tickers:
        try:
            n += sync_trimestres_for(t)
        except Exception as e:
            logger.warning(f"trimestres {t}: {e}")
    lectures = 0
    try:
        lectures = ecrire_lectures(tickers)
    except Exception as e:
        logger.warning(f"trimestres : lectures échouées — {e}")
    return {"tickers": len(tickers), "lignes": n, "lectures": lectures}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) > 1:
        for tk in sys.argv[1:]:
            print(tk, sync_trimestres_for(tk))
    else:
        print(sync_detenus())
