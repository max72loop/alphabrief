"""Backtest de la MOITIÉ PRIX du score (technique + momentum) sur 10 ans.

Question : le bloc prix du moteur (0,25·T + 0,25·M dans le total) trie-t-il les
rendements futurs, et un momentum 12-1 relatif au secteur ferait-il mieux ?

Cette moitié ne dépend que de cours de clôture, connus à la date : on peut la
rejouer sur l'historique sans fuite du futur, ce qu'on ne peut pas faire pour
les fondamentaux (yfinance ne sert pas de fondamentaux datés).

Méthode
-------
- Univers : le S&P 500 du fixture `sp500_tickers.csv` (secteur GICS), ETF SPDR
  du secteur comme référence (SPY avant la création de XLRE/XLC).
- Chaque fin de mois depuis 2016 : indicateurs recalculés sur les seuls cours
  connus à cette date (mêmes formules que core/features/), puis passés au VRAI
  moteur `compute_potential_score` — on mesure la formule en prod, pas une copie.
- Rendement futur : excès sur l'ETF du secteur à 21 et 63 séances.
- Critère : corrélation de rang (Spearman) score → rendement futur, mois par
  mois ; on rapporte sa moyenne, son t (sur des mois disjoints pour 63 j), la
  part de mois positifs, et l'écart quintile haut − quintile bas.

Biais connu : l'univers est la composition ACTUELLE de l'indice (survivants).
Il touche les deux formules comparées de la même façon ; il gonfle le momentum
dans l'absolu, donc on lit la comparaison, pas le niveau.

Usage : python3 scripts/backtest_prix.py [--refresh]   (lecture seule, n'écrit
que data/backtest_prix.json et le cache de cours).
"""

from __future__ import annotations

import csv
import json
import math
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.features.momentum import _SECTOR_ETFS, _DEFAULT_BENCHMARK  # noqa: E402
from core.scoring.potential import compute_potential_score  # noqa: E402

UNIVERS = ROOT / "tests/fixtures/paper_portfolio/data/sp500_tickers.csv"
CACHE = ROOT / "data/cache/backtest_prix_cours.pkl"
SORTIE = ROOT / "data/backtest_prix.json"
DEBUT = "2014-01-01"
PREMIER_MOIS = "2016-01-31"
HORIZONS = (21, 63)


def charger_univers() -> dict[str, str]:
    with UNIVERS.open() as f:
        return {r["ticker"].replace(".", "-"): r["sector"] for r in csv.DictReader(f)}


def charger_cours(tickers: list[str], refresh: bool) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pickle.loads(CACHE.read_bytes())
    data = yf.download(tickers, start=DEBUT, auto_adjust=True, progress=False, threads=True)
    close = data["Close"].dropna(how="all")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(close))
    return close


def indicateurs(close: pd.Series) -> pd.DataFrame:
    """Mêmes formules que core/features/technicals.py et momentum.py, causales :
    la valeur à la date t n'utilise que les cours jusqu'à t."""
    c = close.dropna()
    out = pd.DataFrame(index=c.index)
    out["price"] = c
    out["sma_50"] = c.rolling(50).mean()
    out["sma_200"] = c.rolling(200).mean()
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    out["macd_line"] = macd.rolling(3).mean()
    out["macd_signal"] = sig.rolling(3).mean()
    out["macd_histogram"] = (macd - sig).rolling(3).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["rsi_14"] = (100 - 100 / (1 + up / dn)).rolling(3).mean()
    out["volatility_1y"] = c.pct_change().rolling(251).std() * math.sqrt(252) * 100
    out["max_drawdown_1y"] = (c / c.rolling(252, min_periods=20).max() - 1).rolling(252, min_periods=20).min() * 100
    out["high_52w"] = c.rolling(252).max()
    out["low_52w"] = c.rolling(252).min()
    for nom, n in (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)):
        out[f"momentum_{nom}"] = (c / c.shift(n - 1) - 1) * 100
    return out


def _f(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else float(x)


def score_prod(row: pd.Series, bench: pd.Series, secteur: str) -> tuple[float, float]:
    """(technique, momentum) du moteur de prod, à partir des indicateurs du jour."""
    rel = {}
    for nom, n in (("12m", 252), ("3m", 63), ("1m", 21)):
        s, b = row.get(f"momentum_{nom}"), bench.get(f"momentum_{nom}")
        rel[f"relative_momentum_{nom}"] = _f(s - b) if _f(s) is not None and _f(b) is not None else None
    card = {
        "identity": {"sector_note": secteur},
        "market": {
            "current_price": _f(row["price"]),
            "fifty_two_week_high": _f(row["high_52w"]),
            "fifty_two_week_low": _f(row["low_52w"]),
            **{f"momentum_{k}": _f(row[f"momentum_{k}"]) for k in ("1m", "3m", "6m", "12m")},
            **rel,
        },
        "technicals": {k: _f(row[k]) for k in (
            "rsi_14", "sma_50", "sma_200", "macd_line", "macd_signal", "macd_histogram",
            "volatility_1y", "max_drawdown_1y")},
    }
    r = compute_potential_score(card)
    return float(r["technicals"]), float(r["momentum"])


def spearman(a: pd.Series, b: pd.Series) -> float:
    m = a.notna() & b.notna()
    if m.sum() < 30:
        return float("nan")
    return float(a[m].rank().corr(b[m].rank()))


def resume(ics: pd.Series, spreads: pd.Series, pas: int) -> dict:
    """pas = 1 mois (21 j) ou 3 mois (63 j) : le t se calcule sur des mois
    disjoints, sinon les fenêtres qui se recouvrent gonflent la significativité."""
    ics_d = ics.dropna().iloc[::pas]
    sp_d = spreads.dropna().iloc[::pas]
    n = len(ics_d)
    moy = float(ics_d.mean())
    t = moy / (ics_d.std(ddof=1) / math.sqrt(n)) if n > 2 else float("nan")
    return {
        "ic_moyen": round(moy, 4),
        "t": round(t, 2),
        "mois_ic_positif": round(float((ics_d > 0).mean()), 3),
        "ecart_q5_q1_pct": round(float(sp_d.mean()) * 100, 2),
        "n_mois": n,
    }


def main(refresh: bool = False) -> dict:
    univers = charger_univers()
    etfs = sorted(set(_SECTOR_ETFS.values()) | {_DEFAULT_BENCHMARK})
    close = charger_cours(sorted(univers) + etfs, refresh)

    ind = {t: indicateurs(close[t]) for t in close.columns if close[t].notna().sum() > 300}
    fins_de_mois = [d for d in close.resample("ME").last().index if d >= pd.Timestamp(PREMIER_MOIS)]
    jours = close.index

    def benchmark(secteur: str, date) -> str:
        etf = _SECTOR_ETFS.get(secteur, _DEFAULT_BENCHMARK)
        e = ind.get(etf)
        # ETF trop jeune à cette date (XLRE 2015, XLC 2018) : repli sur SPY
        if e is None or pd.isna(e["momentum_12m"].asof(date)):
            return _DEFAULT_BENCHMARK
        return etf

    lignes = []
    for fin in fins_de_mois:
        i = jours.searchsorted(fin, side="right") - 1
        date = jours[i]
        for t, sect in univers.items():
            df = ind.get(t)
            if df is None or date not in df.index or pd.isna(df.at[date, "momentum_12m"]):
                continue
            b = benchmark(sect, date)
            row, brow = df.loc[date], ind[b].loc[date]
            tech, mom = score_prod(row, brow, sect)
            p = df["price"]
            j = p.index.get_loc(date)
            # 12-1 : rendement de t-252 à t-21, relatif à l'ETF sur la même fenêtre
            if j < 252:
                continue
            bp = ind[b]["price"]
            jb = bp.index.get_loc(date)
            m121 = p.iloc[j - 21] / p.iloc[j - 252] - bp.iloc[jb - 21] / bp.iloc[jb - 252]
            fut = {}
            for h in HORIZONS:
                if j + h < len(p) and jb + h < len(bp):
                    fut[h] = (p.iloc[j + h] / p.iloc[j] - 1) - (bp.iloc[jb + h] / bp.iloc[jb] - 1)
            lignes.append({"date": date, "ticker": t, "tech": tech, "mom": mom,
                           "prod": 0.5 * tech + 0.5 * mom, "m121": m121,
                           "rsi": row["rsi_14"], **{f"fut{h}": v for h, v in fut.items()}})
        print(f"{date.date()} {len(lignes)}", file=sys.stderr, end="\r")

    df = pd.DataFrame(lignes)
    signaux = {
        "prod (T+M actuel)": "prod",
        "technique seule": "tech",
        "momentum seul": "mom",
        "RSI brut": "rsi",
        "12-1 relatif secteur": "m121",
    }
    resultats = {}
    for h in HORIZONS:
        pas = h // 21
        res_h = {}
        for nom, col in signaux.items():
            ics, spreads = {}, {}
            for d, g in df.groupby("date"):
                y = g.get(f"fut{h}")
                if y is None or y.notna().sum() < 30:
                    continue
                ics[d] = spearman(g[col], y)
                q = g[col].rank(pct=True)
                spreads[d] = y[q > 0.8].mean() - y[q <= 0.2].mean()
            res_h[nom] = resume(pd.Series(ics).sort_index(), pd.Series(spreads).sort_index(), pas)
        resultats[f"{h}j"] = res_h

    sortie = {
        "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "univers": f"S&P 500 actuel ({df.ticker.nunique()} titres), excès sur ETF secteur",
        "periode": f"{df.date.min().date()} → {df.date.max().date()}",
        "observations": len(df),
        "resultats": resultats,
    }
    SORTIE.write_text(json.dumps(sortie, ensure_ascii=False, indent=2))
    return sortie


def afficher(s: dict) -> None:
    print(f"\n{s['univers']} · {s['periode']} · {s['observations']} observations")
    for h, res in s["resultats"].items():
        print(f"\nHorizon {h}   {'IC moyen':>9} {'t':>6} {'mois IC>0':>10} {'Q5−Q1':>8} {'n':>4}")
        for nom, r in res.items():
            print(f"  {nom:<22} {r['ic_moyen']:>+9.4f} {r['t']:>6.2f} {r['mois_ic_positif']:>10.0%} "
                  f"{r['ecart_q5_q1_pct']:>+7.2f}% {r['n_mois']:>4}")


if __name__ == "__main__":
    afficher(main(refresh="--refresh" in sys.argv))
