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


def fetch_core_fundamentals(ticker: str) -> Dict[str, Any]:
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

    out: Dict[str, Any] = {
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

    # --- OWNERSHIP & SHORT INTEREST (FIX I3) ---
    # FMP ne fournit pas ces champs sur le tier Starter (endpoints
    # institutional-holders / insider-trading sont payants).
    # On délègue à yfinance pour cette section uniquement.
    _populate_ownership_from_yf(ticker, out)

    # --- I2 FALLBACK: si FMP n'a quasi rien renvoyé, compléter via yfinance ---
    n_valid = sum(
        1 for v in {**out["financials"], **out["valuation"]}.values() if v is not None
    )
    if n_valid < 5:
        _fill_from_yf_fallback(ticker, out)

    return out


def _populate_ownership_from_yf(ticker: str, out: Dict[str, Any]) -> None:
    """Récupère insider/short/institutional ownership via yfinance.

    Champs ciblés (clés Yahoo Ticker.info):
    - heldPercentInsiders → insider_ownership
    - shortPercentOfFloat → short_interest
    - heldPercentInstitutions → institutional_ownership
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}

        insider = info.get("heldPercentInsiders")
        if insider is not None and _is_valid_number(insider):
            out["financials"]["insider_ownership"] = _safe_pct(insider)

        short_pct = info.get("shortPercentOfFloat")
        if short_pct is not None and _is_valid_number(short_pct):
            out["financials"]["short_interest"] = _safe_pct(short_pct)

        inst = info.get("heldPercentInstitutions")
        if inst is not None and _is_valid_number(inst):
            out["financials"]["institutional_ownership"] = _safe_pct(inst)
    except Exception as e:
        logger.debug(f"ownership fallback failed for {ticker}: {e}")


def _fill_from_yf_fallback(ticker: str, out: Dict[str, Any]) -> None:
    """Comble les champs manquants en interrogeant yfinance (Ticker.info).

    Utile pour les tickers internationaux (1211.HK, RIO.AX, 6758.T, etc.) où
    le plan FMP Starter ne fournit pas les fundamentals. On ne remplace JAMAIS
    une valeur déjà présente (FMP fait autorité quand il répond).

    Marque la source = "fmp+yf-fallback" pour traçabilité dans les audits.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        if not info:
            return

        fin = out["financials"]
        val = out["valuation"]

        def _set_fin(key: str, raw: Any, pct: bool = False) -> None:
            if fin.get(key) is None and raw is not None and _is_valid_number(raw):
                fin[key] = _safe_pct(raw) if pct else float(raw)

        def _set_val(key: str, raw: Any) -> None:
            if val.get(key) is None and raw is not None and _is_valid_number(raw):
                val[key] = float(raw)

        # Marges et rentabilité
        _set_fin("ebit_margin", info.get("operatingMargins"), pct=True)
        _set_fin("gross_margin", info.get("grossMargins"), pct=True)
        _set_fin("net_margin", info.get("profitMargins"), pct=True)
        _set_fin("roe", info.get("returnOnEquity"), pct=True)
        _set_fin("roic", info.get("returnOnAssets"), pct=True)
        _set_fin("eps_growth", info.get("earningsGrowth"), pct=True)
        _set_fin("current_ratio", info.get("currentRatio"))

        # Valuation
        _set_val("pe_ttm", info.get("trailingPE"))
        _set_val("forward_pe", info.get("forwardPE"))
        _set_val("peg_ratio", info.get("pegRatio"))
        _set_val("ev_ebitda_ttm", info.get("enterpriseToEbitda"))
        _set_val("ev_sales_ttm", info.get("enterpriseToRevenue"))
        _set_val("pb_ratio", info.get("priceToBook"))

        # Si on a effectivement complété, marquer la source pour le debug audit
        out["source"] = "fmp+yf-fallback"
    except Exception as e:
        logger.debug(f"yf fallback failed for {ticker}: {e}")
