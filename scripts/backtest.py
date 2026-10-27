#!/usr/bin/env python3
"""Backtest AlphaBrief — le barème prédit-il quelque chose ?

Rejoue l'historique de `scores_history` contre la performance réalisée, et
répond à UNE question : une société mieux notée fait-elle mieux qu'une société
moins bien notée ? Le chiffre à retenir est l'ÉCART entre la bande haute et la
bande basse. S'il est négatif, le barème classe à l'envers, et l'écran doit le
dire.

Trois choses distinguent cette version de celle du 2026-05-24, dont le résultat
(perf à 30 j décroissante quand la note monte) était trop fragile pour conclure :

1. **Performance en EXCÈS, pas absolue.** L'ancienne version mesurait la perf
   brute : dans un marché qui monte, toutes les tranches ont l'air bonnes, et la
   question « la note trie-t-elle » restait sans réponse. On retranche l'ETF du
   secteur du titre — le même que le moteur utilise déjà pour le momentum
   relatif (`core.features.momentum._SECTOR_ETFS`), pas un benchmark inventé
   pour l'occasion.

2. **Fenêtres DISJOINTES.** L'ancienne version comptait 2748 observations tirées
   de 47 tickers : des relevés quotidiens des mêmes sociétés, donc autant de
   quasi-doublons. Le N indépendant réel était de l'ordre de la centaine ; chaque
   `n` publié était gonflé d'un facteur ~20 et aucun intervalle de confiance
   n'était calculable. On ne garde ici qu'une observation par ticker et par
   fenêtre, en avançant de la longueur de la fenêtre.

3. **Un intervalle de confiance.** Bootstrap sur les tickers (pas sur les
   observations) : deux relevés du même titre ne sont pas deux témoignages
   indépendants. Sans intervalle, un écart de +2 pts sur 30 observations se lit
   comme un résultat alors que ce n'est que du bruit.

Le découpage se fait sur les BANDES PUBLIÉES (`core.scoring.bands`), pas sur des
tranches arbitraires : c'est le barème que voit Max qu'il s'agit de valider, pas
une échelle de test.

Sortie : data/backtests/backtest_latest.json + backtest_YYYYMMDD.json.

Usage:
    python3 scripts/backtest.py
    python3 scripts/backtest.py --limit-tickers 5    # mode debug
    python3 scripts/backtest.py --windows 30,90
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.features.momentum import _DEFAULT_BENCHMARK, _SECTOR_ETFS  # noqa: E402
from core.scoring import bands  # noqa: E402

DB_PATH = Path("/root/alphabrief/data/mytrader.db")
OUT_DIR = Path("/root/alphabrief/data/backtests")

DEFAULT_WINDOWS = [30, 90]
BOOTSTRAP_ITERATIONS = 2000
# Sous ce nombre de titres notés à une même date, un classement ne veut rien dire.
MIN_OBS_PAR_DATE = 10
CONFIDENCE_LEVEL = 0.90


# ─────────────────────────────────────────────
# Chargement
# ─────────────────────────────────────────────

def load_snapshots(limit_tickers: int = 0) -> dict[str, list[tuple[str, int, float | None]]]:
    """{ticker: [(date_iso, score, price_or_None), ...]} trié par date."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        colonnes = {r["name"] for r in con.execute("PRAGMA table_info(scores_history)")}
        # `price` n'existe que depuis le 2026-09-07 : l'historique antérieur
        # retombe sur yfinance, il n'est pas perdu.
        champ_prix = "price" if "price" in colonnes else "NULL AS price"
        rows = con.execute(
            f"SELECT ticker, score, date(date) AS d, {champ_prix} "
            "FROM scores_history WHERE score IS NOT NULL ORDER BY ticker, d"
        ).fetchall()
    finally:
        con.close()

    par_ticker: dict[str, list[tuple[str, int, float | None]]] = defaultdict(list)
    for r in rows:
        par_ticker[r["ticker"]].append((r["d"], int(r["score"]), r["price"]))

    if limit_tickers:
        gardes = sorted(par_ticker)[:limit_tickers]
        par_ticker = {t: par_ticker[t] for t in gardes}
    return dict(par_ticker)


def load_signaux() -> dict[tuple[str, str], dict[str, float]]:
    """{(ticker, date_iso): {signal: valeur}} — le score, ses sous-scores, ses
    piliers et le score en ombre, pour mesurer CE QUI trie (ou pas).

    Un relevé par ticker et par jour (le dernier du jour). Les colonnes absentes
    d'une base plus ancienne sont simplement ignorées.
    """
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        colonnes = {r["name"] for r in con.execute("PRAGMA table_info(scores_history)")}
        champs = ["ticker", "score", "date(date) AS d"] + [
            c for c in ("score_fundamentals", "score_technicals", "score_momentum",
                        "pillars_json", "engine_version", "ombre_json") if c in colonnes]
        rows = con.execute(
            f"SELECT {', '.join(champs)} FROM scores_history "
            "WHERE score IS NOT NULL ORDER BY ticker, date"
        ).fetchall()
    finally:
        con.close()

    out: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        r = dict(r)
        s: dict[str, float] = {"score": r["score"]}
        for c, nom in (("score_fundamentals", "fondamentaux"), ("score_technicals", "technique"),
                       ("score_momentum", "momentum")):
            if r.get(c) is not None:
                s[nom] = r[c]
        try:
            piliers = (json.loads(r.get("pillars_json") or "{}") or {}).get("pillars") or {}
        except ValueError:
            piliers = {}
        for p, v in piliers.items():
            if v is not None:
                s[f"pilier {p}"] = v
        try:
            o = json.loads(r.get("ombre_json") or "{}") or {}
        except ValueError:
            o = {}
        if o.get("fondamentaux") is not None:
            s["ombre fondamentaux"] = o["fondamentaux"]
        if o.get("m121_rel") is not None:
            s["ombre 12-1 relatif"] = o["m121_rel"]
        s["_version"] = r.get("engine_version") or "avant 2026-09-28"
        out[(r["ticker"], r["d"])] = s
    return out


def _rangs(valeurs: list[float]) -> list[float]:
    ordre = sorted(range(len(valeurs)), key=lambda i: valeurs[i])
    rangs = [0.0] * len(valeurs)
    i = 0
    while i < len(ordre):
        j = i
        while j + 1 < len(ordre) and valeurs[ordre[j + 1]] == valeurs[ordre[i]]:
            j += 1
        for k in range(i, j + 1):
            rangs[ordre[k]] = (i + j) / 2.0
        i = j + 1
    return rangs


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < MIN_OBS_PAR_DATE:
        return None
    rx, ry = _rangs(x), _rangs(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else None


def correlations(obs: list[tuple[str, str, float, dict]]) -> dict[str, dict]:
    """Corrélation de rang signal → excès futur, DATE PAR DATE puis moyennée.

    `obs` = [(date, ticker, excès, signaux)] sur des dates espacées d'une
    fenêtre (donc disjointes). Classer les titres entre eux à une même date
    neutralise le marché du moment ; la moyenne sur les dates et son t disent si
    le tri tient dans la durée. C'est le critère qui décide du poids d'un
    pilier : une corrélation qui n'est pas positive ne mérite aucun poids.
    """
    par_date: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for d, _t, exces, sig in obs:
        par_date[d].append((exces, sig))
    noms = sorted({k for _d, _t, _e, s in obs for k in s if not k.startswith("_")})
    out = {}
    for nom in noms:
        ics, n_obs = [], 0
        for lignes in par_date.values():
            paires = [(s[nom], e) for e, s in lignes if s.get(nom) is not None]
            ic = spearman([p[0] for p in paires], [p[1] for p in paires])
            if ic is not None:
                ics.append(ic)
                n_obs += len(paires)
        if not ics:
            continue
        moy = sum(ics) / len(ics)
        if len(ics) > 2:
            et = (sum((v - moy) ** 2 for v in ics) / (len(ics) - 1)) ** 0.5
            t = moy / (et / len(ics) ** 0.5) if et else None
        else:
            t = None
        out[nom] = {"ic_moyen": round(moy, 3), "t": None if t is None else round(t, 2),
                    "n_dates": len(ics), "n_obs": n_obs}
    return out


def load_sectors() -> dict[str, str]:
    """Secteur par ticker, depuis Postgres. Vide si la base est injoignable —
    tout retombe alors sur SPY, ce que le calcul sait faire."""
    try:
        from core.storage import db
    except Exception:
        return {}
    try:
        rows = db.query("SELECT ticker, sector FROM ticker_scores WHERE sector IS NOT NULL")
    except Exception as e:
        print(f"  ! secteurs indisponibles ({e}) — benchmark SPY pour tous", file=sys.stderr)
        return {}
    out = {}
    for r in rows or []:
        ticker = r["ticker"] if isinstance(r, dict) else r[0]
        secteur = r["sector"] if isinstance(r, dict) else r[1]
        if ticker and secteur:
            out[ticker] = secteur
    return out


def fetch_closes(ticker: str, start: str, end: str) -> dict[str, float]:
    """Clôtures quotidiennes ajustées splits/dividendes. {date_iso: close}."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False,
                         auto_adjust=True, threads=False)
        if df is None or df.empty:
            return {}
        if hasattr(df.columns, "levels"):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return {d.strftime("%Y-%m-%d"): float(c) for d, c in df["Close"].items() if c == c}
    except Exception as e:
        print(f"  ! yfinance fail for {ticker}: {e}", file=sys.stderr)
        return {}


# ─────────────────────────────────────────────
# Prix
# ─────────────────────────────────────────────

def close_at_or_after(closes: dict[str, float], date_iso: str, horizon: int = 5) -> float | None:
    """Clôture du jour, ou du prochain jour ouvré (week-ends, fériés)."""
    base = datetime.strptime(date_iso, "%Y-%m-%d").date()
    for offset in range(horizon):
        iso = (base + timedelta(days=offset)).strftime("%Y-%m-%d")
        if iso in closes:
            return closes[iso]
    return None


def close_after_days(closes: dict[str, float], date_iso: str, days: int) -> float | None:
    """Clôture ~`days` jours calendaires plus tard, au prochain jour ouvré."""
    base = datetime.strptime(date_iso, "%Y-%m-%d").date() + timedelta(days=days)
    for offset in range(8):
        iso = (base + timedelta(days=offset)).strftime("%Y-%m-%d")
        if iso in closes:
            return closes[iso]
    return None


# ─────────────────────────────────────────────
# Statistiques
# ─────────────────────────────────────────────

def bootstrap_ci(valeurs_par_ticker: dict[str, list[float]],
                 iterations: int = BOOTSTRAP_ITERATIONS,
                 niveau: float = CONFIDENCE_LEVEL) -> tuple[float, float] | None:
    """Intervalle de confiance de la moyenne, rééchantillonné PAR TICKER.

    Rééchantillonner les observations traiterait deux relevés d'un même titre
    comme deux témoignages indépendants — c'est exactement l'illusion que
    l'ancienne version entretenait. On tire donc des tickers avec remise.
    """
    tickers = [t for t, vals in valeurs_par_ticker.items() if vals]
    if len(tickers) < 3:
        return None

    rng = random.Random(20260907)  # déterministe : deux exécutions comparables
    moyennes = []
    for _ in range(iterations):
        echantillon: list[float] = []
        for _ in range(len(tickers)):
            echantillon.extend(valeurs_par_ticker[rng.choice(tickers)])
        if echantillon:
            moyennes.append(sum(echantillon) / len(echantillon))
    if not moyennes:
        return None

    moyennes.sort()
    alpha = (1.0 - niveau) / 2.0
    lo = moyennes[int(alpha * len(moyennes))]
    hi = moyennes[min(len(moyennes) - 1, int((1.0 - alpha) * len(moyennes)))]
    return round(lo, 2), round(hi, 2)


def resume_bande(valeurs_par_ticker: dict[str, list[float]]) -> dict:
    plates = [v for vals in valeurs_par_ticker.values() for v in vals]
    n = len(plates)
    if n == 0:
        return {"n": 0, "n_tickers": 0, "excess_pct": None, "hit_rate_pct": None, "ci90": None}
    moyenne = sum(plates) / n
    gagnants = sum(1 for v in plates if v > 0)
    return {
        "n": n,
        "n_tickers": len([t for t, vals in valeurs_par_ticker.items() if vals]),
        "excess_pct": round(moyenne, 2),
        "hit_rate_pct": round(gagnants / n * 100, 1),
        "ci90": bootstrap_ci(valeurs_par_ticker),
    }


# ─────────────────────────────────────────────
# Cœur
# ─────────────────────────────────────────────

def run(windows: list[int], limit_tickers: int = 0) -> dict:
    par_ticker = load_snapshots(limit_tickers)
    if not par_ticker:
        raise SystemExit("scores_history est vide — rien à mesurer.")

    secteurs = load_sectors()
    cles_bandes = [b["key"] for b in bands.BANDS]
    libelles = {b["key"]: b["label"] for b in bands.BANDS}

    toutes_dates = [d for snaps in par_ticker.values() for d, _, _ in snaps]
    debut = min(toutes_dates)
    fin = (datetime.strptime(max(toutes_dates), "%Y-%m-%d")
           + timedelta(days=max(windows) + 20)).strftime("%Y-%m-%d")

    print(f"Backtest {len(par_ticker)} tickers, "
          f"{sum(len(s) for s in par_ticker.values())} relevés bruts "
          f"({debut} → {fin})")
    print(f"Fenêtres : {windows} j · découpage sur les bandes publiées · "
          f"perf en excès du secteur\n")

    # bande -> fenêtre -> ticker -> [excès]
    agg: dict[str, dict[int, dict[str, list[float]]]] = {
        cle: {w: defaultdict(list) for w in windows} for cle in cles_bandes
    }
    cache_benchmark: dict[str, dict[str, float]] = {}
    retenus = 0

    # Corrélations : mêmes dates pour tous les titres, espacées d'une fenêtre,
    # pour classer les titres ENTRE EUX à chaque date.
    signaux = load_signaux()
    dates_notees = sorted({d for (_t, d) in signaux})
    grilles: dict[int, set[str]] = {}
    for w in windows:
        grille, prochaine = set(), None
        for d in dates_notees:
            jour = datetime.strptime(d, "%Y-%m-%d").date()
            if prochaine is None or jour >= prochaine:
                grille.add(d)
                prochaine = jour + timedelta(days=w)
        grilles[w] = grille
    obs_ic: dict[int, list] = {w: [] for w in windows}

    for i, ticker in enumerate(sorted(par_ticker), 1):
        print(f"[{i:>2}/{len(par_ticker)}] {ticker:<9}", end=" ", flush=True)
        closes = fetch_closes(ticker, debut, fin)
        if not closes:
            print("(pas de données)")
            continue

        benchmark = _SECTOR_ETFS.get(secteurs.get(ticker, ""), _DEFAULT_BENCHMARK)
        if benchmark not in cache_benchmark:
            cache_benchmark[benchmark] = fetch_closes(benchmark, debut, fin)
        bench_closes = cache_benchmark[benchmark]

        n_ticker = 0
        for w in windows:
            # Fenêtres disjointes : on avance de `w` jours après chaque
            # observation retenue, donc deux mesures ne se recouvrent jamais.
            derniere_fin: datetime.date | None = None

            for date_iso, score, prix_stocke in par_ticker[ticker]:
                jour = datetime.strptime(date_iso, "%Y-%m-%d").date()
                if derniere_fin is not None and jour < derniere_fin:
                    continue

                base = prix_stocke if prix_stocke else close_at_or_after(closes, date_iso)
                futur = close_after_days(closes, date_iso, w)
                if not base or not futur:
                    continue

                bench_base = close_at_or_after(bench_closes, date_iso)
                bench_futur = close_after_days(bench_closes, date_iso, w)
                if not bench_base or not bench_futur:
                    continue

                perf = (futur - base) / base * 100
                perf_bench = (bench_futur - bench_base) / bench_base * 100
                exces = perf - perf_bench

                cle = bands.band(score)["key"]
                if cle in agg:
                    agg[cle][w][ticker].append(exces)
                    n_ticker += 1
                    derniere_fin = jour + timedelta(days=w)

        for w in windows:
            for d in grilles[w]:
                sig = signaux.get((ticker, d))
                if sig is None:
                    continue
                base, futur = close_at_or_after(closes, d), close_after_days(closes, d, w)
                bb, bf = close_at_or_after(bench_closes, d), close_after_days(bench_closes, d, w)
                if base and futur and bb and bf:
                    obs_ic[w].append((d, ticker, (futur / base - bf / bb) * 100, sig))

        retenus += n_ticker
        print(f"{n_ticker} obs · bench {benchmark}")

    # ── Composition du rapport ──────────────────────────────
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "return": "excess vs sector ETF (core.features.momentum._SECTOR_ETFS, fallback SPY)",
            "windows_disjoint": True,
            "buckets": "bandes publiées (core.scoring.bands)",
            "ci": f"bootstrap {BOOTSTRAP_ITERATIONS} tirages sur les tickers, niveau {CONFIDENCE_LEVEL:.0%}",
        },
        "tickers": len(par_ticker),
        "observations": retenus,
        "windows_days": windows,
        "bands": [],
        "spread": {},
    }

    for cle in cles_bandes:
        ligne = {"band": cle, "label": libelles[cle],
                 "min_score": next(b["min_score"] for b in bands.BANDS if b["key"] == cle)}
        for w in windows:
            ligne[f"d{w}"] = resume_bande(agg[cle][w])
        out["bands"].append(ligne)

    # Le chiffre à retenir : bande haute − bande basse.
    haute, basse = cles_bandes[0], cles_bandes[-1]
    for w in windows:
        h = out["bands"][0][f"d{w}"]["excess_pct"]
        b = out["bands"][-1][f"d{w}"]["excess_pct"]
        out["spread"][f"d{w}"] = {
            "high_band": haute,
            "low_band": basse,
            "points": None if (h is None or b is None) else round(h - b, 2),
            "n_high": out["bands"][0][f"d{w}"]["n"],
            "n_low": out["bands"][-1][f"d{w}"]["n"],
        }

    # Ce qui trie, signal par signal (score, sous-scores, piliers, ombre).
    out["correlations"] = {f"d{w}": correlations(obs_ic[w]) for w in windows}
    versions: dict[str, int] = defaultdict(int)
    for s in signaux.values():
        versions[s["_version"]] += 1
    out["engine_versions"] = dict(versions)

    return out


def afficher(out: dict) -> None:
    print(f"\n=== Performance en excès du secteur, par bande publiée ===")
    windows = out["windows_days"]
    entete = f"{'Bande':<22}" + "".join(f" | {'J+' + str(w):<34}" for w in windows)
    print(entete)
    print("-" * len(entete))
    for ligne in out["bands"]:
        cells = [f"{ligne['label']:<22}"]
        for w in windows:
            d = ligne[f"d{w}"]
            if d["n"] == 0:
                cells.append(f" | {'—':<34}")
            else:
                ci = d["ci90"]
                ci_txt = f"[{ci[0]:+.1f};{ci[1]:+.1f}]" if ci else "[IC n/d]"
                cells.append(
                    f" | n={d['n']:<3} ({d['n_tickers']:>2}t) {d['excess_pct']:>+6.2f}% "
                    f"{ci_txt:<16}"
                )
        print("".join(cells))

    print("\n=== Écart haut/bas — le chiffre à retenir ===")
    for w in windows:
        s = out["spread"][f"d{w}"]
        if s["points"] is None:
            print(f"  J+{w:<3} : non mesurable (n_haut={s['n_high']}, n_bas={s['n_low']})")
            continue
        verdict = "le barème trie" if s["points"] > 0 else "LE BARÈME TRIE À L'ENVERS"
        print(f"  J+{w:<3} : {s['points']:+.2f} pts  "
              f"(n_haut={s['n_high']}, n_bas={s['n_low']})  → {verdict}")

    print("\n=== Corrélation de rang signal → excès futur (moyenne des dates) ===")
    print("    Règle : un signal dont la corrélation n'est pas positive (t ≥ 2) ne mérite aucun poids.")
    for w in windows:
        print(f"  J+{w}")
        for nom, c in sorted(out.get("correlations", {}).get(f"d{w}", {}).items(),
                             key=lambda kv: -kv[1]["ic_moyen"]):
            t = "  n/d" if c["t"] is None else f"{c['t']:+5.2f}"
            print(f"    {nom:<22} IC {c['ic_moyen']:+.3f}  t {t}  ({c['n_dates']} dates, {c['n_obs']} obs)")
    print(f"  Versions de formule dans l'historique : {out.get('engine_versions')}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit-tickers", type=int, default=0, help="Debug : N premiers tickers")
    p.add_argument("--windows", type=str, default=",".join(str(w) for w in DEFAULT_WINDOWS),
                   help="Fenêtres en jours, séparées par des virgules")
    args = p.parse_args()

    windows = [int(w) for w in args.windows.split(",") if w.strip()]
    out = run(windows, args.limit_tickers)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    latest = OUT_DIR / "backtest_latest.json"
    date_du_jour = datetime.now(timezone.utc).strftime("%Y%m%d")
    latest.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (OUT_DIR / f"backtest_{date_du_jour}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))

    afficher(out)
    print(f"\nÉcrit {latest}")


if __name__ == "__main__":
    main()
