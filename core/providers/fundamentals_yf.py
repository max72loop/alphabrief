from __future__ import annotations

from typing import Any, Dict, Optional
import yfinance as yf


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


def fetch_core_fundamentals(ticker: str) -> Dict[str, Any]:
    t = yf.Ticker(ticker)

    # P&L (income statement)
    fin = t.financials  # annual, colonnes = périodes, lignes = postes
    # Cashflow statement
    cf = t.cashflow
    # Balance sheet
    bs = t.balance_sheet
    # Market cap (pour FCF yield si besoin)
    info = t.info or {}

    out = {
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
        "source": "yfinance_financials_cashflow",
    }

    # Variables intermédiaires pour calculs
    revenue = None
    ebitda = None
    fcf = None

    # EBIT margin (approx) = EBIT / Total Revenue
    # Noms de lignes possibles selon la version de yfinance et le type d'entreprise :
    # "Ebit" (standard), "Operating Income" (fréquent pour MSFT, AAPL, etc.)
    try:
        if fin is not None and not fin.empty:
            col0 = fin.columns[0]
            revenue = fin.loc["Total Revenue", col0] if "Total Revenue" in fin.index else None
            ebit = None
            for ebit_name in ["Ebit", "EBIT", "Operating Income"]:
                if ebit_name in fin.index:
                    ebit = fin.loc[ebit_name, col0]
                    break
            if revenue and ebit and float(revenue) != 0:
                out["financials"]["ebit_margin"] = _safe_pct(float(ebit) / float(revenue))
                revenue = float(revenue)  # Garder pour FCF margin
    except Exception:
        pass

    # Gross margin
    try:
        if fin is not None and not fin.empty:
            col0 = fin.columns[0]
            gross_profit = None
            for gp_name in ["Gross Profit"]:
                if gp_name in fin.index:
                    gross_profit = float(fin.loc[gp_name, col0])
                    break
            if gross_profit is not None and revenue and revenue > 0:
                out["financials"]["gross_margin"] = _safe_pct(gross_profit / revenue)
    except Exception:
        pass

    # Revenue CAGR 3y (si 4 années dispo)
    try:
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            cols = list(fin.columns)
            if len(cols) >= 4:
                rev_t = float(fin.loc["Total Revenue", cols[0]])
                rev_t3 = float(fin.loc["Total Revenue", cols[3]])
                cagr = _cagr(rev_t3, rev_t, years=3.0)
                out["financials"]["revenue_cagr_3y"] = cagr
    except Exception:
        pass

    # Revenue YoY rates (taux de croissance annuels) - NOUVEAU
    try:
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            cols = list(fin.columns)  # cols[0] = plus récent
            yoy_rates = []
            for i in range(len(cols) - 1):
                rev_recent = float(fin.loc["Total Revenue", cols[i]])
                rev_older = float(fin.loc["Total Revenue", cols[i + 1]])
                if rev_older > 0:
                    yoy_rates.append(100.0 * (rev_recent - rev_older) / rev_older)
            # Inverser : du plus ancien au plus récent
            yoy_rates.reverse()
            if len(yoy_rates) >= 2:
                out["financials"]["revenue_yoy_rates"] = yoy_rates
    except Exception:
        pass

    # FCF et FCF yield
    try:
        mcap = info.get("marketCap")
        if cf is not None and not cf.empty:
            col0 = cf.columns[0]
            # Essayer différents noms de lignes selon la version de yfinance
            ocf = None
            for ocf_name in ["Total Cash From Operating Activities", "Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]:
                if ocf_name in cf.index:
                    ocf = cf.loc[ocf_name, col0]
                    break

            capex = None
            for capex_name in ["Capital Expenditures", "Capital Expenditure"]:
                if capex_name in cf.index:
                    capex = cf.loc[capex_name, col0]
                    break

            if ocf is not None and capex is not None:
                fcf = float(ocf) + float(capex)  # capex souvent négatif
                out["financials"]["fcf_absolute"] = fcf  # NOUVEAU

                # FCF yield
                if mcap and float(mcap) > 0:
                    out["valuation"]["fcf_yield_ttm"] = _safe_pct(fcf / float(mcap))

                # FCF margin
                if revenue and revenue > 0:
                    out["financials"]["fcf_margin"] = _safe_pct(fcf / revenue)
    except Exception:
        pass

    # Net Income (résultat net) - NOUVEAU
    try:
        if fin is not None and not fin.empty:
            col0 = fin.columns[0]
            for ni_name in ["Net Income", "Net Income Common Stockholders"]:
                if ni_name in fin.index:
                    out["financials"]["net_income"] = float(fin.loc[ni_name, col0])
                    break
    except Exception:
        pass

    # EBITDA (pour Net Debt / EBITDA)
    try:
        ebitda = info.get("ebitda")
        if ebitda is None and fin is not None and not fin.empty:
            col0 = fin.columns[0]
            if "Ebitda" in fin.index:
                ebitda = float(fin.loc["Ebitda", col0])
    except Exception:
        pass

    # Net Debt / EBITDA - NOUVEAU
    try:
        total_debt = info.get("totalDebt")
        total_cash = info.get("totalCash")

        # Essayer depuis le balance sheet si pas dans info
        if (total_debt is None or total_cash is None) and bs is not None and not bs.empty:
            col0 = bs.columns[0]
            if total_debt is None:
                for debt_name in ["Total Debt", "Long Term Debt", "Total Liab"]:
                    if debt_name in bs.index:
                        total_debt = float(bs.loc[debt_name, col0])
                        break
            if total_cash is None:
                for cash_name in ["Cash And Cash Equivalents", "Cash", "Total Cash"]:
                    if cash_name in bs.index:
                        total_cash = float(bs.loc[cash_name, col0])
                        break

        if total_debt is not None and total_cash is not None and ebitda and float(ebitda) > 0:
            net_debt = float(total_debt) - float(total_cash)
            out["financials"]["net_debt_to_ebitda"] = net_debt / float(ebitda)
    except Exception:
        pass

    # Interest Coverage = EBIT / Interest Expense
    try:
        if fin is not None and not fin.empty:
            col0 = fin.columns[0]
            ebit_val = None
            for ebit_name in ["Ebit", "EBIT", "Operating Income"]:
                if ebit_name in fin.index:
                    ebit_val = fin.loc[ebit_name, col0]
                    break
            interest_exp = None
            for ie_name in ["Interest Expense", "Interest Expense Non Operating"]:
                if ie_name in fin.index:
                    interest_exp = float(fin.loc[ie_name, col0])
                    break
            if ebit_val is not None and interest_exp is not None and interest_exp != 0:
                # Interest expense is often negative in yfinance, take absolute value
                out["financials"]["interest_coverage"] = float(ebit_val) / abs(interest_exp)
    except Exception:
        pass

    # Share Dilution 3Y (variation du nombre d'actions)
    try:
        if bs is not None and not bs.empty:
            cols = list(bs.columns)
            shares_recent = None
            shares_old = None
            for s_name in ["Ordinary Shares Number", "Share Issued", "Common Stock"]:
                if s_name in bs.index:
                    shares_recent = float(bs.loc[s_name, cols[0]])
                    if len(cols) >= 4:
                        shares_old = float(bs.loc[s_name, cols[3]])
                    elif len(cols) >= 2:
                        shares_old = float(bs.loc[s_name, cols[-1]])
                    break
            if shares_recent and shares_old and shares_old > 0:
                # Pourcentage de dilution (positif = dilution, négatif = rachat)
                out["financials"]["share_dilution_3y"] = _safe_pct((shares_recent - shares_old) / shares_old)
    except Exception:
        pass

    # Payout Ratio
    try:
        payout = info.get("payoutRatio")
        if payout is not None and payout >= 0:
            out["financials"]["payout_ratio"] = _safe_pct(payout)
    except Exception:
        pass

    # P/E TTM (trailing)
    try:
        pe = info.get("trailingPE")
        if pe is not None and pe > 0:
            out["valuation"]["pe_ttm"] = float(pe)
    except Exception:
        pass

    # Forward P/E
    try:
        fwd_pe = info.get("forwardPE")
        if fwd_pe is not None and fwd_pe > 0:
            out["valuation"]["forward_pe"] = float(fwd_pe)
    except Exception:
        pass

    # PEG Ratio (Yahoo Finance utilise la croissance EPS 5 ans — plus précis que P/E / CAGR CA)
    try:
        peg = info.get("pegRatio")
        if peg is not None and float(peg) > 0:
            out["valuation"]["peg_ratio"] = float(peg)
    except Exception:
        pass

    # EV/EBITDA
    try:
        ev_ebitda = info.get("enterpriseToEbitda")
        if ev_ebitda is not None and ev_ebitda > 0:
            out["valuation"]["ev_ebitda_ttm"] = float(ev_ebitda)
    except Exception:
        pass

    # EV/Sales (Revenue)
    try:
        ev_rev = info.get("enterpriseToRevenue")
        if ev_rev is not None and ev_rev > 0:
            out["valuation"]["ev_sales_ttm"] = float(ev_rev)
    except Exception:
        pass

    # Price to Book
    try:
        pb = info.get("priceToBook")
        if pb is not None and pb > 0:
            out["valuation"]["pb_ratio"] = float(pb)
    except Exception:
        pass

    # ROE (Return on Equity)
    try:
        roe = info.get("returnOnEquity")
        if roe is not None:
            out["financials"]["roe"] = _safe_pct(roe)
    except Exception:
        pass

    # Short Interest = % du float vendu à découvert.
    # Mesure le consensus baissier du marché sur le titre. Un taux élevé indique
    # que beaucoup de traders parient sur une baisse — signal de risque accru.
    # Cas extrême (> 20%) : potentiel de short squeeze, mais risque très élevé.
    try:
        si = info.get("shortPercentOfFloat")
        if si is not None:
            out["financials"]["short_interest"] = _safe_pct(si)  # → en %
    except Exception:
        pass

    # Insider Ownership = % des actions détenues par les dirigeants / fondateurs.
    # Signal d'alignement d'intérêts : plus les insiders sont investis,
    # plus ils partagent le risque avec les actionnaires extérieurs.
    try:
        insiders = info.get("heldPercentInsiders")
        if insiders is not None:
            out["financials"]["insider_ownership"] = _safe_pct(insiders)  # → en %
    except Exception:
        pass

    # Net Profit Margin = Net Income / Revenue (marge nette après impôts et intérêts)
    # Différente de l'EBIT margin : révèle le coût réel de la structure financière
    # (une EBIT margin élevée + net margin faible = levier ou fiscalité lourde).
    try:
        pm = info.get("profitMargins")
        if pm is not None:
            out["financials"]["net_margin"] = _safe_pct(pm)  # → en %
    except Exception:
        pass

    # Current Ratio = Current Assets / Current Liabilities (liquidité court terme)
    try:
        cr = info.get("currentRatio")
        if cr is not None and float(cr) > 0:
            out["financials"]["current_ratio"] = float(cr)
    except Exception:
        pass

    # EPS Growth (croissance des bénéfices par action, YoY)
    # earningsGrowth = taux de croissance du BPA sur les 12 derniers mois vs N-1.
    # Distingue une croissance de CA rentable d'une croissance qui détruit la marge.
    try:
        eg = info.get("earningsGrowth")
        if eg is not None:
            out["financials"]["eps_growth"] = _safe_pct(eg)  # → en %
    except Exception:
        pass

    # ROIC — calculé comme ROA (Return on Assets) depuis yfinance.
    # ROIC = Net Income / Total Assets : mesure l'efficacité globale du capital
    # déployé (equity + dette), indépendante de la structure financière.
    try:
        roa = info.get("returnOnAssets")
        if roa is not None:
            out["financials"]["roic"] = _safe_pct(roa)
    except Exception:
        pass

    # Gross Margin Trend (variation de la marge brute sur 2 ans, en points de %)
    # Un trend positif = marge qui s'améliore = pricing power ou maîtrise des coûts.
    # Un trend négatif = compression des marges = signal d'alerte qualité.
    try:
        if fin is not None and not fin.empty:
            cols = list(fin.columns)
            if (
                len(cols) >= 3
                and "Gross Profit" in fin.index
                and "Total Revenue" in fin.index
            ):
                def _gm(col: Any) -> Optional[float]:
                    gp = float(fin.loc["Gross Profit", col])
                    rev = float(fin.loc["Total Revenue", col])
                    return 100.0 * gp / rev if rev > 0 else None

                gm0 = _gm(cols[0])   # marge brute la plus récente
                gm2 = _gm(cols[2])   # marge brute il y a 2 ans
                if gm0 is not None and gm2 is not None:
                    out["financials"]["gross_margin_trend"] = gm0 - gm2  # en pp
    except Exception:
        pass

    # Accruals Ratio (qualité des bénéfices — anomalie de Sloan, 1996)
    # Formula : (Net Income − Operating Cash Flow) / Total Assets × 100
    # Un ratio bas/négatif = bénéfices couverts par du cash réel → haute qualité.
    # Un ratio élevé = bénéfices "gonflés" par ajustements comptables → signal d'alerte.
    # C'est l'un des facteurs qualitatifs les plus prédictifs en finance quantitative.
    try:
        ni = out["financials"].get("net_income")
        total_assets = info.get("totalAssets")

        # Re-fetch OCF depuis le cashflow statement
        ocf_val = None
        if cf is not None and not cf.empty:
            col0 = cf.columns[0]
            for ocf_name in ["Total Cash From Operating Activities", "Operating Cash Flow",
                             "Cash Flow From Continuing Operating Activities"]:
                if ocf_name in cf.index:
                    ocf_val = float(cf.loc[ocf_name, col0])
                    break

        if ni is not None and ocf_val is not None and total_assets is not None and float(total_assets) > 0:
            accruals = (float(ni) - ocf_val) / float(total_assets) * 100.0
            out["financials"]["accruals_ratio"] = accruals
    except Exception:
        pass

    # Institutional Ownership = % des actions détenues par les investisseurs institutionnels.
    # Les institutionnels (fonds, hedge funds, assurances) font une due diligence approfondie.
    # Un taux élevé = confiance du "smart money" ; trop élevé = risque de vente en bloc.
    try:
        inst = info.get("heldPercentInstitutions")
        if inst is not None:
            out["financials"]["institutional_ownership"] = _safe_pct(inst)  # → en %
    except Exception:
        pass

    # Altman Z-Score (prédiction de détresse financière, Altman 1968)
    # Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5
    # X1 = Working Capital / Total Assets (liquidité relative)
    # X2 = Retained Earnings / Total Assets (rentabilité cumulée)
    # X3 = EBIT / Total Assets (efficacité opérationnelle des actifs)
    # X4 = Market Cap / Total Debt (levier de marché)
    # X5 = Revenue / Total Assets (efficacité des actifs)
    # Zones : Z < 1.81 → détresse | 1.81–2.99 → gris | > 2.99 → sain
    #
    # AMÉLIORATION 1 : le modèle Altman a été calibré sur des entreprises manufacturières.
    # Il n'est PAS valide pour les banques et assureurs dont le levier est structurel
    # (les dépôts = dette par construction, X4 = Mcap/Dette serait massivement sous-estimé).
    #
    # AFFINEMENT Klarna : les sociétés de crédit / BNPL (Klarna, Affirm, SoFi...)
    # classées "Financial Services" ne sont PAS des banques. Elles lèvent de la dette
    # sur les marchés de capitaux (securitisation, obligations) comme n'importe quelle
    # société industrielle. Leur bilan (actif = créances clients, passif = dette structurée)
    # est compatible avec l'Altman Z. On affine donc l'exclusion par l'industrie :
    # seuls les vrais établissements bancaires/assurantiels sont exclus.
    _sector_for_z = info.get("sector", "")
    _industry_for_z = info.get("industry", "").lower()
    _is_bank_or_ins_for_z = (
        "bank" in _industry_for_z
        or "insurance" in _industry_for_z
        or "mortgage" in _industry_for_z
    )
    _skip_altman_z = _sector_for_z in {"Financials", "Financial Services"} and _is_bank_or_ins_for_z
    if not _skip_altman_z:
        try:
            ta = info.get("totalAssets")
            mcap = info.get("marketCap")
            total_debt_z = info.get("totalDebt")

            # X1 : Working Capital = Current Assets - Current Liabilities
            wc = None
            tca = info.get("totalCurrentAssets")
            tcl = info.get("totalCurrentLiabilities")
            if (tca is None or tcl is None) and bs is not None and not bs.empty:
                col0 = bs.columns[0]
                if tca is None:
                    for name in ["Total Current Assets", "Current Assets"]:
                        if name in bs.index:
                            tca = float(bs.loc[name, col0])
                            break
                if tcl is None:
                    for name in ["Total Current Liabilities", "Current Liabilities"]:
                        if name in bs.index:
                            tcl = float(bs.loc[name, col0])
                            break
            if tca is not None and tcl is not None:
                wc = float(tca) - float(tcl)

            # X2 : Retained Earnings depuis le bilan
            re = None
            if bs is not None and not bs.empty:
                col0 = bs.columns[0]
                for name in ["Retained Earnings", "Retained Earnings Accumulated Deficit"]:
                    if name in bs.index:
                        re = float(bs.loc[name, col0])
                        break

            # X3 : EBIT (déjà calculé depuis le P&L)
            ebit_z = None
            if fin is not None and not fin.empty:
                for ebit_name in ["Ebit", "EBIT", "Operating Income"]:
                    if ebit_name in fin.index:
                        ebit_z = float(fin.loc[ebit_name, fin.columns[0]])
                        break

            # Vérifier que toutes les données nécessaires sont présentes
            if (ta is not None and float(ta) > 0
                    and wc is not None
                    and re is not None
                    and ebit_z is not None
                    and mcap is not None
                    and revenue is not None and revenue > 0):
                ta_f = float(ta)
                x1 = wc / ta_f
                x2 = re / ta_f
                x3 = ebit_z / ta_f
                x4 = float(mcap) / float(total_debt_z) if (total_debt_z and float(total_debt_z) > 0) else 10.0
                x5 = revenue / ta_f
                z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
                out["financials"]["altman_z"] = round(z, 3)
        except Exception:
            pass

    # Price / Operating Cash Flow (P/OCF)
    # Ratio de valorisation basé sur l'OCF brut (avant soustraction du capex).
    # Complémentaire au FCF yield : pour les entreprises à capex élevé mais nécessaire
    # (utilities, industriels, telcos), l'OCF reflète mieux la capacité bénéficiaire
    # réelle que le FCF qui pénalise lourdement ces investissements obligatoires.
    try:
        ocf_info = info.get("operatingCashflow")
        mcap_info = info.get("marketCap")
        if ocf_info is not None and mcap_info is not None and float(ocf_info) > 0 and float(mcap_info) > 0:
            out["valuation"]["price_to_ocf"] = float(mcap_info) / float(ocf_info)
    except Exception:
        pass

    return out
