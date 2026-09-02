"""
Récupère les fondamentaux financiers d'un ticker via FMP (stable API).
Remplace l'ancienne version basée sur yfinance.
Conserve exactement la même structure de retour (financials, valuation, source).
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from core.providers.fmp_client import fmp_get

logger = logging.getLogger(__name__)


def _safe_pct(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return 100.0 * float(x)


def _cagr(first: float, last: float, years: float) -> Optional[float]:
    if first is None or last is None:
        return None
    if first <= 0 or last <= 0 or years <= 0:
        return None
    return 100.0 * ((last / first) ** (1.0 / years) - 1.0)


def _get(d: dict, key: str, default=None):
    """Safe get with None coalescing."""
    v = d.get(key)
    return v if v is not None else default


def _is_valid_number(val: Any) -> bool:
    """True si val est un nombre fini (pas None, pas NaN). Accepte les négatifs."""
    if val is None:
        return False
    try:
        f = float(val)
    except (TypeError, ValueError):
        return False
    if math.isnan(f) or math.isinf(f):
        return False
    return True


# Suffixes Yahoo des bourses non couvertes par le tier Starter FMP. On ne fait
# pas les 7 appels FMP pour ces tickers (ils retourneraient [] de toute façon)
# et on bascule directement sur yfinance. Liste explicite plutôt que "contient
# un point" pour ne pas exclure BRK.B, BF.B, etc.
_INTL_SUFFIXES = (
    ".HK", ".T", ".AX", ".L", ".PA", ".TO", ".V",
    ".SS", ".SZ", ".KS", ".KQ", ".SI", ".SA", ".MX", ".BO", ".NS",
)


def _is_international(ticker: str) -> bool:
    return ticker.upper().endswith(_INTL_SUFFIXES)


def _empty_payload() -> Dict[str, Any]:
    return {
        "financials": {
            "ebit_margin": None,
            "gross_margin": None,
            "revenue_cagr_3y": None,
            "revenue_yoy_rates": None,
            "roe": None,
            "fcf_margin": None,
            "net_debt_to_ebitda": None,
            "interest_coverage": None,
            "fcf_absolute": None,
            "net_income": None,
            "share_dilution_3y": None,
            "payout_ratio": None,
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
            "fcf_yield_ttm": None,
            "pe_ttm": None,
            "forward_pe": None,
            "peg_ratio": None,
            "ev_ebitda_ttm": None,
            "ev_sales_ttm": None,
            "pb_ratio": None,
            "price_to_ocf": None,
        },
        "source": "fmp",
    }


def fetch_core_fundamentals(ticker: str) -> Dict[str, Any]:
    if _is_international(ticker):
        out = _empty_payload()
        _complete_from_yf(ticker, out)
        out["source"] = "yf-direct"   # surcharge le "fmp+yf-fallback" posé par _fill
        return out

    # Fetch all data from FMP stable API
    income = fmp_get("income-statement", {"symbol": ticker, "period": "annual", "limit": "4"})
    balance = fmp_get("balance-sheet-statement", {"symbol": ticker, "period": "annual", "limit": "4"})
    cashflow = fmp_get("cash-flow-statement", {"symbol": ticker, "period": "annual", "limit": "4"})
    ratios = fmp_get("ratios-ttm", {"symbol": ticker})
    metrics = fmp_get("key-metrics-ttm", {"symbol": ticker})
    profile_list = fmp_get("profile", {"symbol": ticker})
    ev_list = fmp_get("enterprise-values", {"symbol": ticker, "limit": "1"})

    # Normalize: FMP returns lists
    inc: List[Dict] = income if isinstance(income, list) else []
    bs: List[Dict] = balance if isinstance(balance, list) else []
    cf: List[Dict] = cashflow if isinstance(cashflow, list) else []
    rat: Dict = ratios[0] if isinstance(ratios, list) and ratios else {}
    met: Dict = metrics[0] if isinstance(metrics, list) and metrics else {}
    profile: Dict = profile_list[0] if isinstance(profile_list, list) and profile_list else {}
    ev: Dict = ev_list[0] if isinstance(ev_list, list) and ev_list else {}

    # Most recent income statement
    inc0: Dict = inc[0] if inc else {}

    out: Dict[str, Any] = _empty_payload()

    revenue = _get(inc0, "revenue")
    ebitda = _get(inc0, "ebitda")

    # --- FINANCIALS ---

    # EBIT Margin
    try:
        ebit = _get(inc0, "operatingIncome")
        if revenue and ebit and revenue != 0:
            out["financials"]["ebit_margin"] = _safe_pct(ebit / revenue)
    except Exception:
        pass

    # Gross Margin
    try:
        gross_profit = _get(inc0, "grossProfit")
        if gross_profit is not None and revenue and revenue > 0:
            out["financials"]["gross_margin"] = _safe_pct(gross_profit / revenue)
    except Exception:
        pass

    # Revenue CAGR 3y
    try:
        if len(inc) >= 4:
            rev_t = _get(inc[0], "revenue")
            rev_t3 = _get(inc[3], "revenue")
            cagr = _cagr(rev_t3, rev_t, years=3.0)
            out["financials"]["revenue_cagr_3y"] = cagr
    except Exception:
        pass

    # Revenue YoY rates
    try:
        if len(inc) >= 2:
            yoy_rates = []
            for i in range(len(inc) - 1):
                rev_recent = _get(inc[i], "revenue")
                rev_older = _get(inc[i + 1], "revenue")
                if rev_recent and rev_older and rev_older > 0:
                    yoy_rates.append(100.0 * (rev_recent - rev_older) / rev_older)
            yoy_rates.reverse()
            if len(yoy_rates) >= 2:
                out["financials"]["revenue_yoy_rates"] = yoy_rates
    except Exception:
        pass

    # FCF et FCF yield
    try:
        cf0 = cf[0] if cf else {}
        ocf = _get(cf0, "netCashProvidedByOperatingActivities")
        capex = _get(cf0, "investmentsInPropertyPlantAndEquipment")
        mcap = _get(profile, "marketCap")

        if ocf is not None and capex is not None:
            fcf = float(ocf) + float(capex)  # capex est négatif dans FMP
            out["financials"]["fcf_absolute"] = fcf

            if revenue and revenue > 0:
                out["financials"]["fcf_margin"] = _safe_pct(fcf / revenue)
            if mcap and float(mcap) > 0:
                out["valuation"]["fcf_yield_ttm"] = _safe_pct(fcf / float(mcap))
    except Exception:
        pass

    # Net Income
    try:
        ni = _get(inc0, "netIncome")
        if ni is not None:
            out["financials"]["net_income"] = float(ni)
    except Exception:
        pass

    # Net Debt / EBITDA (from key-metrics-ttm for accuracy)
    try:
        nd_ebitda = _get(met, "netDebtToEBITDATTM")
        if nd_ebitda is not None:
            out["financials"]["net_debt_to_ebitda"] = float(nd_ebitda)
        else:
            bs0 = bs[0] if bs else {}
            total_debt = _get(bs0, "totalDebt") or _get(bs0, "longTermDebt")
            total_cash = _get(bs0, "cashAndCashEquivalents") or _get(bs0, "cashAndShortTermInvestments")
            if total_debt is not None and total_cash is not None and ebitda and float(ebitda) > 0:
                net_debt = float(total_debt) - float(total_cash)
                out["financials"]["net_debt_to_ebitda"] = net_debt / float(ebitda)
    except Exception:
        pass

    # Interest Coverage
    try:
        icr = _get(rat, "interestCoverageRatioTTM")
        if icr is not None and icr != 0:
            out["financials"]["interest_coverage"] = float(icr)
        else:
            ebit_val = _get(inc0, "operatingIncome")
            interest_exp = _get(inc0, "interestExpense")
            if ebit_val is not None and interest_exp is not None and interest_exp != 0:
                out["financials"]["interest_coverage"] = float(ebit_val) / abs(float(interest_exp))
    except Exception:
        pass

    # Share Dilution 3Y
    # FIX M4 : IPO récente avec moins de 4 exercices annuels → la fenêtre 3 ans
    # n'a pas de sens, on retourne None plutôt qu'une valeur calculée sur 1-2 ans
    # qui serait trompeuse (taux non comparable aux autres tickers).
    try:
        if len(inc) < 4:
            if len(inc) >= 2:
                logger.info(
                    f"share_dilution_3y: only {len(inc)} annual statements for {ticker}, "
                    f"returning None (need >= 4 for a 3y window)"
                )
            # else: silencieux — pas assez de données pour calculer quoi que ce soit
        else:
            shares_recent = _get(inc[0], "weightedAverageShsOut")
            shares_old = _get(inc[3], "weightedAverageShsOut")
            if shares_recent and shares_old and shares_old > 0:
                out["financials"]["share_dilution_3y"] = _safe_pct((shares_recent - shares_old) / shares_old)
    except Exception:
        pass

    # Payout Ratio (from ratios TTM)
    try:
        payout = _get(rat, "dividendPayoutRatioTTM")
        if payout is not None and payout >= 0:
            out["financials"]["payout_ratio"] = _safe_pct(payout)
    except Exception:
        pass

    # ROE
    try:
        roe = _get(met, "returnOnEquityTTM")
        if roe is not None:
            out["financials"]["roe"] = _safe_pct(roe)
    except Exception:
        pass

    # Net Margin
    try:
        nm = _get(rat, "netProfitMarginTTM")
        if nm is not None:
            out["financials"]["net_margin"] = _safe_pct(nm)
    except Exception:
        pass

    # Current Ratio
    try:
        cr = _get(rat, "currentRatioTTM")
        if cr is not None and float(cr) > 0:
            out["financials"]["current_ratio"] = float(cr)
    except Exception:
        pass

    # EPS Growth
    try:
        if len(inc) >= 2:
            eps_recent = _get(inc[0], "eps")
            eps_older = _get(inc[1], "eps")
            if eps_recent is not None and eps_older is not None and eps_older != 0:
                out["financials"]["eps_growth"] = 100.0 * (eps_recent - eps_older) / abs(eps_older)
    except Exception:
        pass

    # Gross Margin Trend (variation sur 2 ans, en points de %)
    try:
        if len(inc) >= 3:
            def _gm(stmt: Dict) -> Optional[float]:
                gp = _get(stmt, "grossProfit")
                rev = _get(stmt, "revenue")
                return 100.0 * gp / rev if gp is not None and rev and rev > 0 else None

            gm0 = _gm(inc[0])
            gm2 = _gm(inc[2])
            if gm0 is not None and gm2 is not None:
                out["financials"]["gross_margin_trend"] = gm0 - gm2
    except Exception:
        pass

    # Accruals Ratio (Sloan 1996)
    try:
        ni = out["financials"].get("net_income")
        bs0 = bs[0] if bs else {}
        total_assets = _get(bs0, "totalAssets")
        cf0 = cf[0] if cf else {}
        ocf_val = _get(cf0, "netCashProvidedByOperatingActivities")

        if ni is not None and ocf_val is not None and total_assets is not None and float(total_assets) > 0:
            accruals = (float(ni) - float(ocf_val)) / float(total_assets) * 100.0
            out["financials"]["accruals_ratio"] = accruals
    except Exception:
        pass

    # Altman Z-Score
    _sector = profile.get("sector", "")
    _industry = (profile.get("industry") or "").lower()
    _is_bank_or_ins = (
        "bank" in _industry
        or "insurance" in _industry
        or "mortgage" in _industry
    )
    _skip_altman = _sector in {"Financials", "Financial Services"} and _is_bank_or_ins
    if not _skip_altman:
        try:
            bs0 = bs[0] if bs else {}
            ta = _get(bs0, "totalAssets")
            mcap = _get(profile, "marketCap")
            total_debt_z = _get(bs0, "totalDebt") or _get(bs0, "longTermDebt")

            # X1 : Working Capital
            tca = _get(bs0, "totalCurrentAssets")
            tcl = _get(bs0, "totalCurrentLiabilities")
            wc = float(tca) - float(tcl) if tca is not None and tcl is not None else None

            # X2 : Retained Earnings
            re = _get(bs0, "retainedEarnings")

            # X3 : EBIT
            ebit_z = _get(inc0, "operatingIncome")

            if (ta is not None and float(ta) > 0
                    and wc is not None
                    and re is not None
                    and ebit_z is not None
                    and mcap is not None
                    and revenue is not None and revenue > 0):
                ta_f = float(ta)
                x1 = wc / ta_f
                x2 = float(re) / ta_f
                x3 = float(ebit_z) / ta_f
                x4 = float(mcap) / float(total_debt_z) if (total_debt_z and float(total_debt_z) > 0) else 10.0
                x5 = float(revenue) / ta_f
                z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
                out["financials"]["altman_z"] = round(z, 3)
        except Exception:
            pass

    # --- VALUATION ---

    # P/E TTM
    # NB: on accepte les PE négatifs (entreprises en perte). Le scoring
    # (potential.py compute_pe_score_sector_aware) gère pe <= 0 -> score 0.
    # Filtrer ici à `> 0` éliminait ces signaux négatifs au profit du défaut
    # neutre (50), gonflant artificiellement le score des sociétés en pertes.
    try:
        pe = _get(rat, "priceToEarningsRatioTTM")
        if _is_valid_number(pe):
            out["valuation"]["pe_ttm"] = float(pe)
    except Exception:
        pass

    # Forward P/E
    # FMP stable API: le champ `forwardPETTM` existe sur certains endpoints
    # ratios-ttm / key-metrics-ttm. On essaye plusieurs candidats.
    try:
        fwd_pe = (
            _get(rat, "forwardPETTM")
            or _get(met, "forwardPETTM")
            or _get(rat, "forwardPriceEarningsRatioTTM")
            or _get(met, "forwardPriceEarningsRatioTTM")
        )
        if _is_valid_number(fwd_pe):
            out["valuation"]["forward_pe"] = float(fwd_pe)
    except Exception:
        pass

    # PEG Ratio
    try:
        peg = _get(rat, "priceToEarningsGrowthRatioTTM")
        if _is_valid_number(peg):
            out["valuation"]["peg_ratio"] = float(peg)
    except Exception:
        pass

    # EV/EBITDA — accepter négatifs (EBITDA négatif = pertes opérationnelles,
    # le scorer met le score à 0 dans ce cas, signal négatif réel).
    try:
        ev_ebitda = _get(met, "evToEBITDATTM")
        if _is_valid_number(ev_ebitda):
            out["valuation"]["ev_ebitda_ttm"] = float(ev_ebitda)
    except Exception:
        pass

    # EV/Sales — accepter négatifs (rare : CA négatif sur ajustements compta).
    try:
        ev_sales = _get(met, "evToSalesTTM")
        if _is_valid_number(ev_sales):
            out["valuation"]["ev_sales_ttm"] = float(ev_sales)
    except Exception:
        pass

    # Price to Book — accepter négatifs (equity négative = signal de détresse
    # financière qu'il faut faire remonter, pas masquer).
    try:
        pb = _get(rat, "priceToBookRatioTTM")
        if _is_valid_number(pb):
            out["valuation"]["pb_ratio"] = float(pb)
    except Exception:
        pass

    # Price / Operating Cash Flow
    try:
        pocf = _get(rat, "priceToOperatingCashFlowRatioTTM")
        if _is_valid_number(pocf):
            out["valuation"]["price_to_ocf"] = float(pocf)
    except Exception:
        pass

    # ROIC (via key-metrics)
    try:
        roa = _get(met, "returnOnAssetsTTM")
        if roa is not None:
            out["financials"]["roic"] = _safe_pct(roa)
    except Exception:
        pass

    # --- COMPLÉTION yfinance (2026-09-02) ---
    # Inconditionnelle, et non plus soumise à `n_valid < 5`. On ne complète que
    # les champs restés vides, donc FMP garde autorité partout où il répond.
    # Voir le commentaire de _complete_from_yf pour le détail du raisonnement.
    _complete_from_yf(ticker, out)

    return out




# ═══════════════════════════════════════════════════════════════════════════
# Complétion yfinance
# ═══════════════════════════════════════════════════════════════════════════
#
# Historique : cette couche s'appelait « fallback » et ne se déclenchait que si
# FMP n'avait « quasi rien » renvoyé (`n_valid < 5`). Deux défauts l'ont rendue
# inopérante là où elle comptait le plus :
#
#   1. Elle ne couvrait que 13 champs — pas ceux qui manquaient réellement.
#      Relevé du 2026-09-02 sur les 39 cartes en cache : fcf_margin,
#      fcf_absolute, net_income, fcf_yield_ttm, revenue_cagr_3y,
#      revenue_yoy_rates, interest_coverage, payout_ratio, share_dilution_3y,
#      net_debt_to_ebitda, price_to_ocf, gross_margin_trend, accruals_ratio et
#      altman_z manquaient sur 29 à 32 cartes sur 39. Aucun n'était comblé ici.
#
#      En poids de scoring, ça retirait ~80 % du pilier Croissance (le CAGR 3 ans
#      pèse 0,45 à lui seul et `compute_cagr_score_sector_aware(None)` renvoie 50
#      neutre), ~45 % du Risque et ~41 % de la Qualité. C'est l'explication
#      complète de la compression des scores entre 32 et 68.
#
#   2. Le seuil `n_valid < 5` était compté APRÈS que l'ownership yfinance ait
#      déjà rempli jusqu'à 3 champs, donc le compteur mesurait en partie le
#      travail de yfinance lui-même avant de décider s'il fallait appeler
#      yfinance. Fragile par construction.
#
# FMP est par ailleurs mort : au 2026-09-02 tous les endpoints répondent
# HTTP 429 « Limit Reach . Please upgrade your plan », y compris `profile`.
# Ce n'est pas un rate-limit transitoire — le backoff 5s/15s/45s du client ne
# peut pas aboutir. yfinance n'est donc plus un secours mais la source réelle.
#
# D'où le renversement : on complète TOUJOURS, sans condition. C'est sans risque
# puisqu'on n'écrase jamais une valeur déjà posée (FMP garde autorité s'il
# répond un jour), et c'est idempotent. Un seul objet `yf.Ticker` sert les
# quatre jeux de données — avant, deux fonctions en créaient chacune un et
# refaisaient l'appel `.info`.


def _f(x: Any) -> Optional[float]:
    """float() tolérant : None, NaN, chaînes vides et pandas NA donnent None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # NaN


def _col(df: Any, label: str, idx: int = 0) -> Optional[float]:
    """Valeur d'une ligne d'états financiers yfinance à la colonne `idx`.

    Les colonnes sont ordonnées du plus récent au plus ancien — même convention
    que les listes FMP, donc les calculs en aval se transposent tels quels.
    """
    try:
        if df is None or getattr(df, "empty", True) or label not in df.index:
            return None
        row = df.loc[label]
        if idx >= len(row):
            return None
        return _f(row.iloc[idx])
    except Exception:
        return None


def _ncols(df: Any) -> int:
    try:
        return 0 if df is None or getattr(df, "empty", True) else len(df.columns)
    except Exception:
        return 0


def _yf_bundle(ticker: str) -> Dict[str, Any]:
    """`.info` + les trois états financiers, en un seul objet Ticker.

    Chaque jeu est isolé : yfinance échoue régulièrement sur un état précis
    (petites capitalisations, tickers internationaux) sans que les autres soient
    affectés. Un échec partiel doit dégrader le résultat, pas l'annuler.
    """
    bundle: Dict[str, Any] = {"info": {}, "income": None, "balance": None, "cash": None}
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
    except Exception as e:
        logger.debug(f"yfinance indisponible pour {ticker}: {e}")
        return bundle

    try:
        bundle["info"] = tk.info or {}
    except Exception as e:
        logger.debug(f"yf info {ticker}: {e}")
    for key, attr in (("income", "income_stmt"), ("balance", "balance_sheet"), ("cash", "cashflow")):
        try:
            bundle[key] = getattr(tk, attr)
        except Exception as e:
            logger.debug(f"yf {attr} {ticker}: {e}")
    return bundle


def _complete_from_yf(ticker: str, out: Dict[str, Any]) -> None:
    """Comble tout champ encore vide à partir de yfinance.

    N'écrase JAMAIS une valeur déjà présente. Chaque champ est calculé dans son
    propre try/except : un état financier biscornu ne doit pas emporter les
    treize autres champs avec lui.
    """
    b = _yf_bundle(ticker)
    info, inc, bal, cf = b["info"], b["income"], b["balance"], b["cash"]
    if not info and _ncols(inc) == 0:
        return

    fin = out["financials"]
    val = out["valuation"]
    filled: list[str] = []

    def put_fin(key: str, value: Optional[float]) -> None:
        if fin.get(key) is None and value is not None and _is_valid_number(value):
            fin[key] = float(value)
            filled.append(key)

    def put_val(key: str, value: Optional[float]) -> None:
        if val.get(key) is None and value is not None and _is_valid_number(value):
            val[key] = float(value)
            filled.append(key)

    # ── Détention et flottant ────────────────────────────────────────────────
    # FMP ne les vend pas sur le tier Starter (institutional-holders et
    # insider-trading sont des endpoints payants) : yfinance en est la seule
    # source depuis le début.
    put_fin("insider_ownership", _safe_pct(_f(info.get("heldPercentInsiders"))))
    put_fin("short_interest", _safe_pct(_f(info.get("shortPercentOfFloat"))))
    put_fin("institutional_ownership", _safe_pct(_f(info.get("heldPercentInstitutions"))))

    # ── Marges et rentabilité ────────────────────────────────────────────────
    put_fin("ebit_margin", _safe_pct(_f(info.get("operatingMargins"))))
    put_fin("gross_margin", _safe_pct(_f(info.get("grossMargins"))))
    put_fin("net_margin", _safe_pct(_f(info.get("profitMargins"))))
    put_fin("roe", _safe_pct(_f(info.get("returnOnEquity"))))
    put_fin("roic", _safe_pct(_f(info.get("returnOnAssets"))))
    put_fin("eps_growth", _safe_pct(_f(info.get("earningsGrowth"))))
    put_fin("current_ratio", _f(info.get("currentRatio")))
    put_fin("payout_ratio", _safe_pct(_f(info.get("payoutRatio"))))

    # ── Multiples ────────────────────────────────────────────────────────────
    put_val("pe_ttm", _f(info.get("trailingPE")))
    put_val("forward_pe", _f(info.get("forwardPE")))
    put_val("peg_ratio", _f(info.get("pegRatio")))
    put_val("ev_ebitda_ttm", _f(info.get("enterpriseToEbitda")))
    put_val("ev_sales_ttm", _f(info.get("enterpriseToRevenue")))
    put_val("pb_ratio", _f(info.get("priceToBook")))

    revenue_ttm = _f(info.get("totalRevenue"))
    mcap = _f(info.get("marketCap"))
    fcf = _f(info.get("freeCashflow"))
    ocf = _f(info.get("operatingCashflow"))
    net_inc = _f(info.get("netIncomeToCommon"))

    # ── Trésorerie : le trou le plus coûteux ─────────────────────────────────
    # fcf_margin pèse 0,18 dans Qualité, fcf_yield_ttm 0,16 dans Valeur (son
    # composant le plus lourd), et cash_conv 0,15 exige fcf_absolute ET
    # net_income ensemble.
    put_fin("fcf_absolute", fcf)
    put_fin("net_income", net_inc)
    try:
        if fcf is not None and revenue_ttm and revenue_ttm > 0:
            put_fin("fcf_margin", 100.0 * fcf / revenue_ttm)
    except Exception:
        pass
    try:
        if fcf is not None and mcap and mcap > 0:
            put_val("fcf_yield_ttm", 100.0 * fcf / mcap)
    except Exception:
        pass
    try:
        if ocf and ocf > 0 and mcap and mcap > 0:
            put_val("price_to_ocf", mcap / ocf)
    except Exception:
        pass

    # ── Levier ───────────────────────────────────────────────────────────────
    try:
        debt = _f(info.get("totalDebt"))
        cash_ = _f(info.get("totalCash"))
        ebitda = _f(info.get("ebitda"))
        if debt is not None and ebitda and ebitda > 0:
            net_debt = debt - (cash_ or 0.0)
            put_fin("net_debt_to_ebitda", net_debt / ebitda)
    except Exception:
        pass

    # ── Séries de revenus ────────────────────────────────────────────────────
    # 0,45 du pilier Croissance à lui seul, plus 0,20 de tendance et 0,15 de
    # stabilité qui dérivent de la même série. Sans elle, Croissance vaut 50
    # neutre quel que soit le titre.
    revs = []
    if _ncols(inc) >= 2:
        revs = [_col(inc, "Total Revenue", i) for i in range(_ncols(inc))]

    try:
        # Colonnes du plus récent au plus ancien, comme les listes FMP.
        if len(revs) >= 4 and revs[0] and revs[3]:
            put_fin("revenue_cagr_3y", _cagr(revs[3], revs[0], years=3.0))
        elif len(revs) >= 3 and revs[0] and revs[2]:
            # Repli sur 2 ans annualisés plutôt que rien : une société qui n'a
            # que trois exercices publiés reste jugeable sur sa croissance.
            put_fin("revenue_cagr_3y", _cagr(revs[2], revs[0], years=2.0))
    except Exception:
        pass

    try:
        if len(revs) >= 3:
            yoy = []
            for i in range(len(revs) - 1):
                recent, older = revs[i], revs[i + 1]
                if recent and older and older > 0:
                    yoy.append(100.0 * (recent - older) / older)
            yoy.reverse()  # du plus ancien au plus récent, convention FMP
            if len(yoy) >= 2 and fin.get("revenue_yoy_rates") is None:
                fin["revenue_yoy_rates"] = yoy
                filled.append("revenue_yoy_rates")
    except Exception:
        pass

    # ── Couverture des intérêts ──────────────────────────────────────────────
    # yfinance laisse « Interest Expense » vide sur les exercices récents de
    # certaines sociétés : on balaie les colonnes jusqu'à en trouver une, plutôt
    # que d'abandonner sur la première.
    try:
        ebit_val = _col(inc, "Operating Income", 0)
        interest = None
        for i in range(_ncols(inc)):
            cand = _col(inc, "Interest Expense", i)
            if cand:
                interest = abs(cand)
                break
        if ebit_val is not None and interest:
            put_fin("interest_coverage", ebit_val / interest)
    except Exception:
        pass

    # ── Tendance de marge brute (variation sur 2 ans, en points) ─────────────
    try:
        if _ncols(inc) >= 3:
            def gm(i: int) -> Optional[float]:
                gp, rv = _col(inc, "Gross Profit", i), _col(inc, "Total Revenue", i)
                return 100.0 * gp / rv if gp is not None and rv and rv > 0 else None
            gm0, gm2 = gm(0), gm(2)
            if gm0 is not None and gm2 is not None:
                put_fin("gross_margin_trend", gm0 - gm2)
    except Exception:
        pass

    # ── Dilution sur 3 ans ───────────────────────────────────────────────────
    try:
        if _ncols(inc) >= 4:
            label = "Diluted Average Shares" if "Diluted Average Shares" in getattr(inc, "index", []) \
                else "Basic Average Shares"
            s_now, s_old = _col(inc, label, 0), _col(inc, label, 3)
            if s_now and s_old and s_old > 0:
                put_fin("share_dilution_3y", 100.0 * (s_now - s_old) / s_old)
    except Exception:
        pass

    # ── Accruals (Sloan 1996) ────────────────────────────────────────────────
    try:
        ni_a = _col(inc, "Net Income", 0) or net_inc
        ocf_a = _col(cf, "Operating Cash Flow", 0) or ocf
        ta = _col(bal, "Total Assets", 0)
        if ni_a is not None and ocf_a is not None and ta and ta > 0:
            put_fin("accruals_ratio", 100.0 * (ni_a - ocf_a) / ta)
    except Exception:
        pass

    # ── Altman Z ─────────────────────────────────────────────────────────────
    # Sans objet pour les banques et assureurs : leur bilan n'a ni fonds de
    # roulement ni structure de passif comparables à ceux d'une société
    # industrielle. Même exclusion que la branche FMP, et même exclusion que
    # `is_financial` dans potential.py.
    try:
        industry = (info.get("industry") or "").lower()
        sector = info.get("sector") or ""
        is_bank_or_ins = ("bank" in industry or "insurance" in industry or "mortgage" in industry)
        if not (sector in {"Financials", "Financial Services"} and is_bank_or_ins):
            ta = _col(bal, "Total Assets", 0)
            tca = _col(bal, "Current Assets", 0)
            tcl = _col(bal, "Current Liabilities", 0)
            re_ = _col(bal, "Retained Earnings", 0)
            tl = _col(bal, "Total Liabilities Net Minority Interest", 0)
            ebit_z = _col(inc, "Operating Income", 0)
            sales = _col(inc, "Total Revenue", 0) or revenue_ttm
            if (ta and ta > 0 and tca is not None and tcl is not None and re_ is not None
                    and ebit_z is not None and mcap and tl and tl > 0 and sales):
                z = (1.2 * ((tca - tcl) / ta)
                     + 1.4 * (re_ / ta)
                     + 3.3 * (ebit_z / ta)
                     + 0.6 * (mcap / tl)
                     + 1.0 * (sales / ta))
                put_fin("altman_z", z)
    except Exception:
        pass

    if filled:
        base = out.get("source") or "fmp"
        if "yf" not in base:
            out["source"] = f"{base}+yf"
        logger.debug(f"{ticker}: {len(filled)} champs complétés par yfinance")
