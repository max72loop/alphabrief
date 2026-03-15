from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _f(x: Any) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except Exception:
        return None


@dataclass
class Item:
    label: str
    importance: float
    why: str
    direction: str  # "positive" | "negative" | "neutral"


def _add(items: List[Item], label: str, importance: float, why: str, direction: str) -> None:
    items.append(Item(label=label, importance=importance, why=why, direction=direction))


def build_importance_items(card: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    fin = card.get("financials", {})
    val = card.get("valuation", {})
    mkt = card.get("market", {})
    tech = card.get("technicals", {})
    ident = card.get("identity", {})

    ebit = _f(fin.get("ebit_margin"))          # %
    gross_margin = _f(fin.get("gross_margin")) # %
    cagr = _f(fin.get("revenue_cagr_3y"))      # %
    roe = _f(fin.get("roe"))                   # %
    fcf_margin = _f(fin.get("fcf_margin"))     # %
    net_debt_ebitda = _f(fin.get("net_debt_to_ebitda"))  # ratio
    interest_coverage = _f(fin.get("interest_coverage"))  # ratio
    share_dilution = _f(fin.get("share_dilution_3y"))  # %
    payout_ratio = _f(fin.get("payout_ratio"))  # %
    yoy_rates = fin.get("revenue_yoy_rates")   # liste de taux YoY
    fcfy = _f(val.get("fcf_yield_ttm"))        # %
    pe = _f(val.get("pe_ttm"))                 # ratio
    ev_ebitda = _f(val.get("ev_ebitda_ttm"))   # ratio
    ev_sales = _f(val.get("ev_sales_ttm"))     # ratio
    pb = _f(val.get("pb_ratio"))               # ratio
    mom = _f(mkt.get("momentum_12m"))          # %
    beta = _f(mkt.get("beta"))
    rsi = _f(tech.get("rsi_14"))
    mcap = _f(ident.get("market_cap"))
    div_yield = _f(mkt.get("dividend_yield"))  # décimal (ex: 0.03 = 3%)
    sma_50 = _f(tech.get("sma_50"))
    sma_200 = _f(tech.get("sma_200"))
    current_price = _f(mkt.get("current_price"))
    forward_pe = _f(val.get("forward_pe"))
    fcf_abs = _f(fin.get("fcf_absolute"))
    net_inc = _f(fin.get("net_income"))
    low_52w = _f(mkt.get("fifty_two_week_low"))
    high_52w = _f(mkt.get("fifty_two_week_high"))
    volatility_1y = _f(tech.get("volatility_1y"))
    max_drawdown_1y = _f(tech.get("max_drawdown_1y"))
    accruals_ratio = _f(fin.get("accruals_ratio"))

    items: List[Item] = []

    # === QUALITY ===

    # EBIT margin
    if ebit is not None:
        if ebit >= 25:
            _add(items, "Marge EBIT très élevée", 85, f"EBIT margin ~{ebit:.1f}% : forte capacité à générer du profit.", "positive")
        elif ebit >= 12:
            _add(items, "Marge EBIT solide", 70, f"EBIT margin ~{ebit:.1f}% : rentabilité correcte.", "positive")
        elif ebit < 0:
            # Perte opérationnelle — distinct de "marge faible" (ex: Figma à -117%, Airbnb à -3%)
            _add(items, "Perte opérationnelle (EBIT négatif)", 90,
                 f"EBIT margin ~{ebit:.1f}% : l'entreprise brûle du cash opérationnel.", "negative")
        elif ebit <= 5:
            _add(items, "Marge EBIT faible", 85, f"EBIT margin ~{ebit:.1f}% : sensibilité élevée aux chocs.", "negative")
        else:
            _add(items, "Marge EBIT moyenne", 55, f"EBIT margin ~{ebit:.1f}% : rentabilité intermédiaire.", "neutral")

    # Gross margin
    if gross_margin is not None:
        if gross_margin >= 50:
            _add(items, "Marge brute très élevée", 75, f"Gross margin ~{gross_margin:.1f}% : fort pouvoir de pricing.", "positive")
        elif gross_margin >= 35:
            _add(items, "Marge brute solide", 55, f"Gross margin ~{gross_margin:.1f}% : bonne marge.", "positive")
        elif gross_margin <= 20:
            _add(items, "Marge brute faible", 70, f"Gross margin ~{gross_margin:.1f}% : faible pouvoir de pricing.", "negative")

    # FCF margin
    if fcf_margin is not None:
        if fcf_margin >= 15:
            _add(items, "Excellente génération de cash", 80, f"FCF margin ~{fcf_margin:.1f}% : très forte conversion en cash.", "positive")
        elif fcf_margin >= 8:
            _add(items, "Bonne génération de cash", 65, f"FCF margin ~{fcf_margin:.1f}% : conversion satisfaisante.", "positive")
        elif fcf_margin < 0:
            # FCF négatif — distinguer de "faible positif" : signifie que l'entreprise consomme
            # du cash net (capex + WC > OCF), souvent volontaire en phase de croissance.
            _add(items, "FCF négatif (consommation de cash)", 75,
                 f"FCF margin ~{fcf_margin:.1f}% : plus de cash consommé que généré.", "negative")
        elif fcf_margin <= 2:
            _add(items, "Faible génération de cash", 75, f"FCF margin ~{fcf_margin:.1f}% : difficulté à convertir en cash.", "negative")

    # Revenue CAGR 3y
    if cagr is not None:
        if cagr >= 15:
            _add(items, "Croissance du CA forte (3 ans)", 80, f"CAGR CA ~{cagr:.1f}% : expansion rapide.", "positive")
        elif cagr >= 5:
            _add(items, "Croissance du CA modérée (3 ans)", 60, f"CAGR CA ~{cagr:.1f}% : progression régulière.", "positive")
        elif cagr <= 0:
            _add(items, "CA en stagnation/baisse (3 ans)", 80, f"CAGR CA ~{cagr:.1f}% : risque de maturité.", "negative")
        else:
            _add(items, "Croissance du CA faible (3 ans)", 65, f"CAGR CA ~{cagr:.1f}% : croissance limitée.", "neutral")

    # Tendance de croissance (accélération/décélération) - NOUVEAU
    if yoy_rates is not None:
        yoy_rates = [r for r in yoy_rates if r is not None and not math.isnan(r)]
    if yoy_rates is not None and len(yoy_rates) >= 2:
        deltas = [yoy_rates[i+1] - yoy_rates[i] for i in range(len(yoy_rates)-1)]
        accelerating = sum(1 for d in deltas if d > 1.0)
        decelerating = sum(1 for d in deltas if d < -1.0)
        last_yoy = yoy_rates[-1]
        if accelerating == len(deltas) and last_yoy > 5:
            _add(items, "Croissance en accélération", 80, f"CA YoY en hausse chaque année (dernier : {last_yoy:.1f}%) : dynamique forte.", "positive")
        elif decelerating == len(deltas):
            _add(items, "Croissance en décélération", 75, f"CA YoY en baisse chaque année (dernier : {last_yoy:.1f}%) : ralentissement.", "negative")
        elif accelerating > decelerating:
            _add(items, "Tendance croissance favorable", 60, f"CA YoY globalement en hausse (dernier : {last_yoy:.1f}%).", "positive")
        elif decelerating > accelerating:
            _add(items, "Tendance croissance défavorable", 60, f"CA YoY globalement en baisse (dernier : {last_yoy:.1f}%).", "negative")

    # Stabilité de la croissance revenue
    if yoy_rates is not None and len(yoy_rates) >= 2:
        avg_yoy = sum(yoy_rates) / len(yoy_rates)
        # Variance non-biaisée (correction de Bessel, diviseur n-1) — cohérent avec potential.py
        var_yoy = sum((r - avg_yoy) ** 2 for r in yoy_rates) / (len(yoy_rates) - 1)
        std_yoy = var_yoy ** 0.5
        cv_yoy = std_yoy / abs(avg_yoy) if abs(avg_yoy) >= 1.0 else std_yoy
        all_pos = all(r > 0 for r in yoy_rates)
        has_drop = any(r < -10.0 for r in yoy_rates)

        if cv_yoy <= 0.25 and all_pos:
            _add(items, "Croissance très régulière", 75,
                 f"CV ~{cv_yoy:.2f}, toujours positif : revenus prévisibles et fiables.", "positive")
        elif cv_yoy <= 0.40:
            _add(items, "Croissance stable", 55,
                 f"CV ~{cv_yoy:.2f} : régularité correcte des revenus.", "positive")
        elif cv_yoy >= 1.0 or has_drop:
            _add(items, "Croissance erratique", 70,
                 f"CV ~{cv_yoy:.2f} : revenus imprévisibles, risque accru.", "negative")
        elif cv_yoy >= 0.70:
            _add(items, "Croissance volatile", 55,
                 f"CV ~{cv_yoy:.2f} : variations importantes d'une année à l'autre.", "negative")

    # ROE
    if roe is not None:
        if roe >= 20:
            _add(items, "ROE excellent", 75, f"ROE ~{roe:.1f}% : très bonne rentabilité des capitaux.", "positive")
        elif roe >= 12:
            _add(items, "ROE solide", 60, f"ROE ~{roe:.1f}% : rentabilité satisfaisante.", "positive")
        elif roe >= 5:
            _add(items, "ROE modéré", 45, f"ROE ~{roe:.1f}% : rentabilité correcte mais perfectible.", "neutral")
        elif roe >= 0:
            _add(items, "ROE faible", 70, f"ROE ~{roe:.1f}% : faible retour sur capitaux.", "negative")
        else:
            _add(items, "ROE négatif", 85, f"ROE ~{roe:.1f}% : capitaux propres négatifs ou pertes.", "negative")

    # Cash Conversion (qualité des bénéfices) - NOUVEAU
    if fcf_abs is not None and net_inc is not None and net_inc > 0:
        ratio = fcf_abs / net_inc
        if ratio >= 1.2:
            _add(items, "Bénéfices de haute qualité", 80, f"FCF/Net Income ~{ratio:.1f}x : profits bien convertis en cash.", "positive")
        elif ratio >= 0.8:
            _add(items, "Bonne qualité des bénéfices", 55, f"FCF/Net Income ~{ratio:.1f}x : conversion correcte.", "positive")
        elif ratio < 0.5:
            _add(items, "Qualité des bénéfices faible", 80, f"FCF/Net Income ~{ratio:.1f}x : profits comptables, peu de cash réel.", "negative")

    # Accruals Ratio (anomalie de Sloan, 1996) — qualité comptable des bénéfices
    # Formula : (Net Income − OCF) / Total Assets × 100
    # Un ratio élevé signale que les profits déclarés dépassent le cash encaissé :
    # souvent précurseur d'une révision à la baisse des résultats.
    if accruals_ratio is not None:
        if accruals_ratio < -3:
            _add(items, "Bénéfices cash-backed (accruals bas)", 85,
                 f"Accruals ratio ~{accruals_ratio:.1f}% : bénéfices largement couverts par le cash réel.", "positive")
        elif accruals_ratio < 3:
            _add(items, "Qualité comptable acceptable", 45,
                 f"Accruals ratio ~{accruals_ratio:.1f}% : bénéfices en ligne avec le cash.", "neutral")
        elif accruals_ratio < 8:
            _add(items, "Accruals élevés (alerte qualité)", 80,
                 f"Accruals ratio ~{accruals_ratio:.1f}% : bénéfices supérieurs au cash généré — risque comptable.", "negative")
        else:
            _add(items, "Accruals très élevés (drapeau rouge)", 90,
                 f"Accruals ratio ~{accruals_ratio:.1f}% : forte inflation comptable possible — anomalie de Sloan.", "negative")

    # Share Dilution
    if share_dilution is not None:
        if share_dilution <= -5:
            _add(items, "Rachats d'actions massifs", 80, f"Dilution 3Y ~{share_dilution:.1f}% : retour de cash aux actionnaires.", "positive")
        elif share_dilution <= -2:
            _add(items, "Rachats d'actions", 65, f"Dilution 3Y ~{share_dilution:.1f}% : nombre d'actions en baisse.", "positive")
        elif share_dilution >= 10:
            _add(items, "Forte dilution actionnaires", 80, f"Dilution 3Y ~{share_dilution:.1f}% : dilution importante.", "negative")
        elif share_dilution >= 5:
            _add(items, "Dilution modérée", 60, f"Dilution 3Y ~{share_dilution:.1f}% : émission d'actions.", "negative")

    # === VALUE ===

    # FCF yield
    if fcfy is not None:
        if fcfy >= 6:
            _add(items, "FCF yield attractif", 75, f"FCF yield ~{fcfy:.1f}% : prix raisonnable vs cash généré.", "positive")
        elif fcfy <= 2:
            _add(items, "FCF yield tendu", 75, f"FCF yield ~{fcfy:.1f}% : valorisation élevée vs cash.", "negative")
        else:
            _add(items, "FCF yield moyen", 55, f"FCF yield ~{fcfy:.1f}% : niveau intermédiaire.", "neutral")

    # P/E TTM
    if pe is not None:
        if pe <= 0:
            _add(items, "Bénéfices négatifs (perte)", 90, f"P/E ~{pe:.1f}x : l'entreprise est déficitaire.", "negative")
        elif pe <= 12:
            _add(items, "P/E attractif (value)", 80, f"P/E ~{pe:.1f}x : valorisation basse.", "positive")
        elif pe <= 20:
            _add(items, "P/E raisonnable", 55, f"P/E ~{pe:.1f}x : valorisation dans la moyenne.", "neutral")
        elif pe <= 35:
            _add(items, "P/E élevé (growth pricing)", 65, f"P/E ~{pe:.1f}x : anticipation de forte croissance.", "neutral")
        else:
            _add(items, "P/E très élevé (risque)", 80, f"P/E ~{pe:.1f}x : valorisation tendue.", "negative")

    # PEG Ratio — priorité au pegRatio Yahoo Finance (croissance EPS 5 ans),
    # sinon calcul interne depuis P/E TTM / CAGR CA
    peg_stored = _f(val.get("peg_ratio"))
    if peg_stored is not None and peg_stored > 0:
        peg = peg_stored
    elif pe is not None and cagr is not None and cagr > 0:
        peg = pe / cagr
    else:
        peg = None

    if peg is not None and peg > 0:
        source_label = "(YF)" if peg_stored is not None else "(calc.)"
        if peg <= 1.0:
            _add(items, "PEG attractif", 85, f"PEG ~{peg:.2f} {source_label} : sous-valorisé vs croissance.", "positive")
        elif peg <= 1.5:
            _add(items, "PEG raisonnable", 60, f"PEG ~{peg:.2f} {source_label} : valorisation correcte vs croissance.", "neutral")
        elif peg <= 2.5:
            _add(items, "PEG élevé", 70, f"PEG ~{peg:.2f} {source_label} : valorisation tendue vs croissance.", "negative")
        else:
            _add(items, "PEG très élevé", 75, f"PEG ~{peg:.2f} {source_label} : surévalué par rapport à la croissance.", "negative")

    # Forward P/E
    if forward_pe is not None:
        if forward_pe <= 12:
            _add(items, "Forward P/E attractif", 80, f"Forward P/E ~{forward_pe:.1f}x : valorisation future basse.", "positive")
        elif forward_pe >= 35:
            _add(items, "Forward P/E très élevé", 75, f"Forward P/E ~{forward_pe:.1f}x : valorisation future tendue.", "negative")

        # Comparaison Forward vs Trailing
        if pe is not None and pe > 0:
            ratio = forward_pe / pe
            if ratio <= 0.75:
                _add(items, "Forte croissance bénéfices attendue", 85,
                     f"Forward P/E ({forward_pe:.1f}x) << Trailing P/E ({pe:.1f}x) : analystes anticipent +{(1/ratio - 1)*100:.0f}% de bénéfices.", "positive")
            elif ratio <= 0.90:
                _add(items, "Croissance bénéfices attendue", 65,
                     f"Forward P/E ({forward_pe:.1f}x) < Trailing P/E ({pe:.1f}x) : hausse des bénéfices anticipée.", "positive")
            elif ratio >= 1.20:
                _add(items, "Baisse bénéfices attendue", 80,
                     f"Forward P/E ({forward_pe:.1f}x) > Trailing P/E ({pe:.1f}x) : analystes anticipent une baisse.", "negative")

    # EV/EBITDA
    if ev_ebitda is not None:
        if ev_ebitda <= 0:
            _add(items, "EBITDA négatif (pertes opérationnelles)", 90, f"EV/EBITDA ~{ev_ebitda:.1f}x : EBITDA négatif, l'entreprise brûle du cash.", "negative")
        elif ev_ebitda <= 8:
            _add(items, "EV/EBITDA attractif", 75, f"EV/EBITDA ~{ev_ebitda:.1f}x : valorisation attractive.", "positive")
        elif ev_ebitda <= 15:
            _add(items, "EV/EBITDA raisonnable", 50, f"EV/EBITDA ~{ev_ebitda:.1f}x : niveau standard.", "neutral")
        else:
            _add(items, "EV/EBITDA élevé", 70, f"EV/EBITDA ~{ev_ebitda:.1f}x : prime importante.", "negative")

    # EV/Sales
    if ev_sales is not None:
        if ev_sales <= 1.5:
            _add(items, "EV/Sales très bas", 70, f"EV/Sales ~{ev_sales:.1f}x : valorisation très attractive vs revenus.", "positive")
        elif ev_sales <= 2.5:
            _add(items, "EV/Sales bas", 65, f"EV/Sales ~{ev_sales:.1f}x : faible multiple de revenus.", "positive")
        elif ev_sales >= 12:
            _add(items, "EV/Sales extrême", 75, f"EV/Sales ~{ev_sales:.1f}x : prime de valorisation extrême.", "negative")
        elif ev_sales >= 8:
            _add(items, "EV/Sales élevé", 70, f"EV/Sales ~{ev_sales:.1f}x : valorisation premium.", "negative")

    # Price to Book - AMÉLIORÉ
    if pb is not None:
        if pb <= 1.0:
            _add(items, "P/B très attractif", 75, f"P/B ~{pb:.1f}x : sous la valeur comptable.", "positive")
        elif pb <= 2.0:
            _add(items, "P/B attractif", 60, f"P/B ~{pb:.1f}x : proche de la valeur des actifs.", "positive")
        elif pb >= 10:
            _add(items, "P/B très élevé", 65, f"P/B ~{pb:.1f}x : forte prime sur les actifs.", "negative")

    # Dividend Yield - NOUVEAU
    if div_yield is not None and div_yield > 0:
        pct = div_yield * 100
        if pct >= 4:
            _add(items, "Dividende élevé", 75, f"Rendement ~{pct:.1f}% : revenu passif attractif.", "positive")
        elif pct >= 2:
            _add(items, "Dividende correct", 55, f"Rendement ~{pct:.1f}% : complément de revenu.", "positive")
        elif pct >= 0.5:
            _add(items, "Dividende faible", 35, f"Rendement ~{pct:.1f}% : dividende symbolique.", "neutral")

    # Payout Ratio (soutenabilité du dividende)
    if payout_ratio is not None and div_yield is not None and div_yield > 0:
        if payout_ratio > 100:
            _add(items, "Dividende non soutenable", 85, f"Payout ratio ~{payout_ratio:.0f}% : dividende non couvert par les bénéfices.", "negative")
        elif payout_ratio > 80:
            _add(items, "Payout ratio élevé", 65, f"Payout ratio ~{payout_ratio:.0f}% : peu de marge pour maintenir le dividende.", "negative")
        elif payout_ratio < 40 and div_yield * 100 >= 2:
            _add(items, "Dividende très soutenable", 70, f"Payout ratio ~{payout_ratio:.0f}% : large marge de sécurité.", "positive")

    # === MOMENTUM & TECHNICAL ===

    # Momentum 12m
    if mom is not None:
        if mom >= 25:
            _add(items, "Momentum très positif (12m)", 70, f"Perf 12m ~{mom:.1f}% : tendance haussière forte.", "positive")
        elif mom >= 10:
            _add(items, "Momentum positif (12m)", 55, f"Perf 12m ~{mom:.1f}% : tendance favorable.", "positive")
        elif mom <= -20:
            _add(items, "Momentum très négatif (12m)", 75, f"Perf 12m ~{mom:.1f}% : tendance baissière marquée.", "negative")
        elif mom <= -10:
            _add(items, "Momentum négatif (12m)", 60, f"Perf 12m ~{mom:.1f}% : tendance défavorable.", "negative")

    # RSI
    if rsi is not None:
        if rsi <= 30:
            _add(items, "RSI survendu (opportunité)", 80, f"RSI ~{rsi:.0f} : potentiel de rebond technique.", "positive")
        elif rsi >= 70:
            _add(items, "RSI suracheté (prudence)", 75, f"RSI ~{rsi:.0f} : risque de correction technique.", "negative")

    # Signal SMA - NOUVEAU
    if current_price is not None and sma_50 is not None and sma_200 is not None:
        if sma_50 > sma_200 and current_price > sma_50:
            _add(items, "Golden cross + prix haussier", 75, f"SMA50 > SMA200, prix au-dessus : tendance haussière confirmée.", "positive")
        elif sma_50 < sma_200 and current_price < sma_50:
            _add(items, "Death cross + prix baissier", 75, f"SMA50 < SMA200, prix en-dessous : tendance baissière confirmée.", "negative")
        elif sma_50 > sma_200 and current_price < sma_50:
            _add(items, "Correction dans tendance haussière", 55, f"SMA50 > SMA200 mais prix sous SMA50 : repli temporaire possible.", "neutral")
        elif sma_50 < sma_200 and current_price > sma_50:
            _add(items, "Rebond dans tendance baissière", 55, f"SMA50 < SMA200 mais prix au-dessus : rebond technique.", "neutral")
    elif current_price is not None and sma_200 is not None:
        if current_price > sma_200 * 1.10:
            _add(items, "Prix bien au-dessus SMA200", 60, f"Prix +{((current_price/sma_200)-1)*100:.0f}% vs SMA200 : tendance forte.", "positive")
        elif current_price < sma_200 * 0.90:
            _add(items, "Prix bien en-dessous SMA200", 65, f"Prix {((current_price/sma_200)-1)*100:.0f}% vs SMA200 : faiblesse marquée.", "negative")

    # MACD
    macd_line = _f(tech.get("macd_line"))
    macd_signal_val = _f(tech.get("macd_signal"))
    macd_hist = _f(tech.get("macd_histogram"))
    if macd_hist is not None and current_price is not None and current_price > 0:
        hist_pct = (macd_hist / current_price) * 100
        if hist_pct >= 0.5:
            _add(items, "MACD fortement haussier", 70,
                 f"Histogramme MACD ~{hist_pct:.2f}% du prix : fort momentum haussier.", "positive")
        elif hist_pct >= 0.1:
            _add(items, "MACD haussier", 55,
                 f"Histogramme MACD positif (~{hist_pct:.2f}%) : momentum favorable.", "positive")
        elif hist_pct <= -0.5:
            _add(items, "MACD fortement baissier", 70,
                 f"Histogramme MACD ~{hist_pct:.2f}% du prix : fort momentum baissier.", "negative")
        elif hist_pct <= -0.1:
            _add(items, "MACD baissier", 55,
                 f"Histogramme MACD négatif (~{hist_pct:.2f}%) : momentum défavorable.", "negative")

    # Position 52 semaines
    if current_price is not None and low_52w is not None and high_52w is not None and high_52w > low_52w:
        position = (current_price - low_52w) / (high_52w - low_52w)
        pct_pos = position * 100
        if position <= 0.20:
            _add(items, "Proche du plus bas 52 sem", 80,
                 f"Prix à {pct_pos:.0f}% du range 52 sem : proche du plancher, opportunité potentielle.", "positive")
        elif position <= 0.35:
            _add(items, "Zone basse du range 52 sem", 60,
                 f"Prix à {pct_pos:.0f}% du range 52 sem : zone favorable pour l'achat.", "positive")
        elif position >= 0.90:
            _add(items, "Au plus haut 52 semaines", 75,
                 f"Prix à {pct_pos:.0f}% du range 52 sem : risque de correction élevé.", "negative")
        elif position >= 0.80:
            _add(items, "Proche du plus haut 52 sem", 60,
                 f"Prix à {pct_pos:.0f}% du range 52 sem : prudence, déjà bien monté.", "negative")

    # === RISK ===

    # Beta
    if beta is not None:
        if beta >= 1.5:
            _add(items, "Beta très élevé (volatilité)", 70, f"Beta ~{beta:.2f} : très sensible au marché.", "negative")
        elif beta >= 1.3:
            _add(items, "Beta élevé", 55, f"Beta ~{beta:.2f} : volatilité supérieure au marché.", "negative")
        elif beta <= 0.7:
            _add(items, "Beta défensif", 50, f"Beta ~{beta:.2f} : profil défensif.", "positive")

    # Interest Coverage
    if interest_coverage is not None:
        if interest_coverage >= 10:
            _add(items, "Excellente couverture des intérêts", 65, f"Interest Coverage ~{interest_coverage:.1f}x : dette très bien couverte.", "positive")
        elif interest_coverage < 2:
            _add(items, "Couverture des intérêts critique", 85, f"Interest Coverage ~{interest_coverage:.1f}x : risque de défaut.", "negative")
        elif interest_coverage < 3:
            _add(items, "Couverture des intérêts faible", 75, f"Interest Coverage ~{interest_coverage:.1f}x : marge de sécurité limitée.", "negative")

    # Volatilité 1Y
    if volatility_1y is not None:
        if volatility_1y >= 50:
            _add(items, "Volatilité extrême", 75, f"Volatilité annualisée ~{volatility_1y:.0f}% : mouvements de prix très importants.", "negative")
        elif volatility_1y >= 35:
            _add(items, "Forte volatilité", 55, f"Volatilité annualisée ~{volatility_1y:.0f}% : risque de fluctuations élevé.", "negative")
        elif volatility_1y <= 15:
            _add(items, "Faible volatilité", 50, f"Volatilité annualisée ~{volatility_1y:.0f}% : prix très stable.", "positive")

    # Max Drawdown 1Y
    if max_drawdown_1y is not None:
        dd = abs(max_drawdown_1y)
        if dd >= 40:
            _add(items, "Drawdown sévère (1 an)", 80, f"Max drawdown ~{dd:.0f}% : perte maximale importante sur 1 an.", "negative")
        elif dd >= 25:
            _add(items, "Drawdown significatif (1 an)", 60, f"Max drawdown ~{dd:.0f}% : correction notable.", "negative")
        elif dd <= 10:
            _add(items, "Drawdown faible (1 an)", 50, f"Max drawdown ~{dd:.0f}% : très bonne résilience.", "positive")

    # Net Debt / EBITDA
    if net_debt_ebitda is not None:
        if net_debt_ebitda < 0:
            _add(items, "Trésorerie nette positive", 80, f"Net Debt/EBITDA ~{net_debt_ebitda:.1f}x : aucune dette nette.", "positive")
        elif net_debt_ebitda <= 1.0:
            _add(items, "Faible endettement", 70, f"Net Debt/EBITDA ~{net_debt_ebitda:.1f}x : bilan solide.", "positive")
        elif net_debt_ebitda <= 2.5:
            _add(items, "Endettement modéré", 50, f"Net Debt/EBITDA ~{net_debt_ebitda:.1f}x : niveau gérable.", "neutral")
        elif net_debt_ebitda <= 4.0:
            _add(items, "Endettement élevé", 70, f"Net Debt/EBITDA ~{net_debt_ebitda:.1f}x : attention au levier.", "negative")
        else:
            _add(items, "Endettement critique", 85, f"Net Debt/EBITDA ~{net_debt_ebitda:.1f}x : risque financier élevé.", "negative")

    # === ANALYST CONSENSUS ===
    analyst_target = _f(mkt.get("analyst_target_mean"))
    analyst_count = mkt.get("analyst_count")
    analyst_reco = mkt.get("analyst_recommendation")

    if analyst_target is not None and current_price is not None and current_price > 0:
        upside_pct = (analyst_target - current_price) / current_price * 100
        n_analysts = int(analyst_count) if analyst_count is not None else 0
        suffix = f" ({n_analysts} analystes)" if n_analysts > 0 else ""

        if upside_pct >= 25:
            _add(items, "Fort upside analystes", 85,
                 f"Target moyen {analyst_target:.0f} vs prix {current_price:.0f} : +{upside_pct:.0f}% d'upside{suffix}.", "positive")
        elif upside_pct >= 10:
            _add(items, "Upside analystes modéré", 70,
                 f"Target moyen {analyst_target:.0f} vs prix {current_price:.0f} : +{upside_pct:.0f}% d'upside{suffix}.", "positive")
        elif upside_pct >= -5:
            _add(items, "Target analystes ~ prix actuel", 45,
                 f"Target moyen {analyst_target:.0f} vs prix {current_price:.0f} : {upside_pct:+.0f}%{suffix}.", "neutral")
        elif upside_pct >= -15:
            _add(items, "Downside selon analystes", 75,
                 f"Target moyen {analyst_target:.0f} vs prix {current_price:.0f} : {upside_pct:.0f}%{suffix}.", "negative")
        else:
            _add(items, "Fort downside analystes", 85,
                 f"Target moyen {analyst_target:.0f} vs prix {current_price:.0f} : {upside_pct:.0f}%{suffix}.", "negative")

    # Recommendation key
    if analyst_reco is not None:
        reco_labels = {
            "strong_buy":   ("Consensus Strong Buy",   75, "positive"),
            "buy":          ("Consensus Buy",           65, "positive"),
            "outperform":   ("Consensus Outperform",    58, "positive"),   # clé YF réelle
            "hold":         ("Consensus Hold",          45, "neutral"),
            "underperform": ("Consensus Underperform",  70, "negative"),
            "sell":         ("Consensus Sell",          80, "negative"),
            "strong_sell":  ("Consensus Strong Sell",   85, "negative"),   # clé YF réelle
        }
        if analyst_reco in reco_labels:
            lbl, imp, direc = reco_labels[analyst_reco]
            n_a = int(analyst_count) if analyst_count is not None else 0
            suffix_r = f" ({n_a} analystes)" if n_a > 0 else ""
            _add(items, lbl, imp, f"Recommendation : {analyst_reco}{suffix_r}.", direc)

    # Taille (context)
    if mcap is not None:
        if mcap >= 200e9:
            _add(items, "Mega-cap (stabilité)", 35, "Taille très importante : stabilité mais croissance plus difficile.", "neutral")
        elif mcap <= 2e9:
            _add(items, "Small-cap (risque + upside)", 55, "Petite capitalisation : potentiel élevé mais risque supérieur.", "neutral")

    # Tri par importance décroissante + limite
    items.sort(key=lambda x: x.importance, reverse=True)
    items = items[:max(0, int(limit))]

    return [
        {
            "label": it.label,
            "importance_score": int(round(it.importance)),
            "why_it_matters": it.why,
            "direction": it.direction,
        }
        for it in items
    ]
