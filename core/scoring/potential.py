from __future__ import annotations

import math
from typing import Any, Dict, Optional


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def score_linear(value: Optional[float], lo: float, hi: float, default: float = 50.0) -> float:
    """
    Mappe value sur 0-100.
    - value <= lo => 0
    - value >= hi => 100
    """
    if value is None or math.isnan(value):
        return default
    return 100.0 * clamp((value - lo) / (hi - lo), 0.0, 1.0)


def score_linear_inverse(value: Optional[float], lo: float, hi: float, default: float = 50.0) -> float:
    """
    Mappe value sur 0-100 inversement (plus bas = meilleur).
    - value >= hi => 0
    - value <= lo => 100
    """
    if value is None or math.isnan(value):
        return default
    if value <= lo:
        return 100.0
    if value >= hi:
        return 0.0
    return 100.0 * (1.0 - (value - lo) / (hi - lo))


def compute_peg_score(peg: Optional[float]) -> float:
    """
    PEG Ratio = P/E / Growth Rate
    - PEG < 1 = sous-valorisé
    - PEG 1-2 = fair value
    - PEG > 2 = surévalué

    Accepte le PEG directement (depuis Yahoo Finance pegRatio ou calculé en amont).
    Retourne un score 0-100 (plus bas PEG = meilleur score).
    """
    if peg is None or peg <= 0:
        return 50.0  # Neutre si pas de données

    if peg <= 0.5:
        return 100.0
    elif peg <= 1.0:
        return 85.0
    elif peg <= 1.5:
        return 70.0
    elif peg <= 2.0:
        return 55.0
    elif peg <= 3.0:
        return 35.0
    else:
        return 15.0


def compute_forward_pe_score(forward_pe: Optional[float], trailing_pe: Optional[float]) -> float:
    """
    Score basé sur le Forward P/E et sa comparaison avec le Trailing P/E.
    - Forward P/E bas = valorisation attractive sur les bénéfices futurs
    - Forward < Trailing = croissance des bénéfices attendue (positif)
    - Forward > Trailing = baisse des bénéfices attendue (négatif)

    Score composite : 60% niveau absolu + 40% dynamique (forward vs trailing)
    """
    if forward_pe is None or forward_pe <= 0:
        return 50.0

    # Score absolu du Forward P/E (même logique que trailing, plus bas = mieux)
    abs_score = score_linear_inverse(forward_pe, lo=10.0, hi=35.0)

    # Score dynamique : ratio Forward / Trailing
    if trailing_pe is not None and trailing_pe > 0:
        ratio = forward_pe / trailing_pe
        # ratio < 1 = bénéfices en hausse attendus
        # ratio > 1 = bénéfices en baisse attendus
        if ratio <= 0.6:
            dyn_score = 95.0  # Forte croissance attendue
        elif ratio <= 0.8:
            dyn_score = 80.0  # Bonne croissance attendue
        elif ratio <= 0.95:
            dyn_score = 65.0  # Légère croissance attendue
        elif ratio <= 1.05:
            dyn_score = 50.0  # Stable
        elif ratio <= 1.2:
            dyn_score = 35.0  # Légère baisse attendue
        else:
            dyn_score = 15.0  # Forte baisse attendue

        return 0.60 * abs_score + 0.40 * dyn_score
    else:
        return abs_score


def compute_52w_position_score(price: Optional[float], low_52w: Optional[float], high_52w: Optional[float]) -> float:
    """
    Score basé sur la position du prix dans le range 52 semaines.
    Position = (prix - low) / (high - low) → 0% = au plus bas, 100% = au plus haut.

    Orienté "opportunité d'achat" :
    - Proche du plus bas (0-20%) : forte opportunité si fondamentaux OK
    - Zone basse (20-40%) : opportunité modérée
    - Zone médiane (40-60%) : neutre
    - Zone haute (60-80%) : prudence, déjà bien valorisé
    - Proche du plus haut (80-100%) : risque de correction
    """
    if price is None or low_52w is None or high_52w is None:
        return 50.0
    if high_52w <= low_52w:
        return 50.0

    position = (price - low_52w) / (high_52w - low_52w)  # 0.0 à 1.0

    if position <= 0.15:
        return 85.0  # Très proche du plus bas = forte opportunité
    elif position <= 0.30:
        return 72.0  # Zone basse = opportunité
    elif position <= 0.45:
        return 60.0  # Zone mi-basse = légèrement favorable
    elif position <= 0.60:
        return 50.0  # Zone médiane = neutre
    elif position <= 0.75:
        return 40.0  # Zone mi-haute = prudence
    elif position <= 0.90:
        return 30.0  # Zone haute = risque de correction
    else:
        return 18.0  # Au plus haut 52 sem = risque élevé


def compute_revenue_stability_score(yoy_rates: Optional[list]) -> float:
    """
    Score de stabilité/constance de la croissance du CA.
    Mesure le coefficient de variation des taux YoY.

    - CV faible (< 0.3) : croissance très régulière = haute qualité
    - CV moyen (0.3-0.7) : croissance modérément stable
    - CV élevé (> 0.7) : croissance erratique = moins fiable
    - Bonus si toutes les années sont positives (jamais de baisse)

    AMÉLIORATION 3 : utilise la variance non-biaisée (diviseur N-1, correction de
    Bessel) au lieu de la variance de population (diviseur N). Avec seulement 2 à 4
    points de données (le cas typique ici), la variance de population sous-estime
    systématiquement la dispersion réelle : la correction de Bessel compense ce biais
    et rend le score de stabilité plus conservateur et statistiquement correct.
    """
    if yoy_rates is None or len(yoy_rates) < 2:
        return 50.0

    n = len(yoy_rates)
    avg = sum(yoy_rates) / n
    # Variance non-biaisée : diviseur (n-1) — correction de Bessel
    variance = sum((r - avg) ** 2 for r in yoy_rates) / (n - 1)
    std_dev = variance ** 0.5

    # Coefficient de variation (normalisé par la valeur absolue de la moyenne)
    if abs(avg) < 1.0:
        cv = std_dev / 1.0  # Éviter division par ~0 quand croissance quasi nulle
    else:
        cv = std_dev / abs(avg)

    # Score de base sur le CV
    if cv <= 0.15:
        score = 90.0  # Croissance ultra-régulière
    elif cv <= 0.30:
        score = 78.0  # Très stable
    elif cv <= 0.50:
        score = 65.0  # Raisonnablement stable
    elif cv <= 0.70:
        score = 50.0  # Moyenne
    elif cv <= 1.0:
        score = 35.0  # Erratique
    else:
        score = 20.0  # Très erratique

    # Bonus : toutes les années en croissance positive
    all_positive = all(r > 0 for r in yoy_rates)
    if all_positive:
        score = min(100.0, score + 10.0)

    # Pénalité : une année très négative (< -10%)
    has_big_drop = any(r < -10.0 for r in yoy_rates)
    if has_big_drop:
        score = max(0.0, score - 12.0)

    return score


def compute_debt_score(net_debt_ebitda: Optional[float]) -> float:
    """
    Score basé sur Net Debt / EBITDA
    - < 1x : Excellent (faible dette)
    - 1-2x : Bon
    - 2-3x : Moyen
    - 3-4x : Élevé
    - > 4x : Risqué

    Valeurs négatives = trésorerie nette positive (très bien)
    """
    if net_debt_ebitda is None:
        return 50.0

    if net_debt_ebitda < 0:
        return 95.0  # Trésorerie nette positive
    elif net_debt_ebitda <= 1.0:
        return 85.0
    elif net_debt_ebitda <= 2.0:
        return 70.0
    elif net_debt_ebitda <= 3.0:
        return 50.0
    elif net_debt_ebitda <= 4.0:
        return 30.0
    else:
        return 15.0


def compute_rsi_score(rsi: Optional[float]) -> float:
    """
    Score basé sur RSI (14 jours)
    - RSI < 30 : Survendu (potentiel de rebond) = bonus
    - RSI 30-70 : Neutre
    - RSI > 70 : Suracheté (risque de correction) = pénalité

    Score orienté "opportunité d'achat"
    """
    if rsi is None:
        return 50.0

    if rsi <= 25:
        return 85.0  # Très survendu = forte opportunité
    elif rsi <= 35:
        return 70.0  # Survendu = opportunité
    elif rsi <= 50:
        return 60.0  # Zone basse = légèrement favorable
    elif rsi <= 65:
        return 50.0  # Neutre
    elif rsi <= 75:
        return 40.0  # Zone haute = prudence
    elif rsi <= 85:
        return 25.0  # Suracheté = risque
    else:
        return 10.0  # Très suracheté = risque élevé


def compute_dividend_score(div_yield: Optional[float], payout_ratio: Optional[float] = None) -> float:
    """
    Score basé sur le rendement du dividende + soutenabilité (payout ratio).
    - Pas de dividende : neutre (50)
    - Dividende élevé + payout bas = très attractif (soutenable)
    - Dividende élevé + payout élevé = risque de coupure
    """
    if div_yield is None or div_yield <= 0:
        return 50.0  # Neutre, pas pénalisant
    pct = div_yield * 100  # Convertir en pourcentage
    if pct >= 6:
        base = 90.0
    elif pct >= 4:
        base = 80.0
    elif pct >= 2:
        base = 70.0
    elif pct >= 1:
        base = 60.0
    else:
        base = 55.0

    # Ajustement par le payout ratio (soutenabilité du dividende)
    if payout_ratio is not None and payout_ratio > 0:
        if payout_ratio > 100:
            base = max(20.0, base - 25.0)  # Dividende non couvert par les bénéfices
        elif payout_ratio > 80:
            base = max(30.0, base - 12.0)  # Payout élevé, peu de marge
        elif payout_ratio < 40:
            base = min(100.0, base + 5.0)  # Payout bas, très soutenable

    return base


def compute_growth_trend_score(yoy_rates: Optional[list]) -> float:
    """
    Score basé sur la tendance de croissance (accélération / décélération)
    ET sur le niveau absolu du dernier taux YoY.

    yoy_rates = [croissance année -2, année -1, année 0] (du plus ancien au plus récent)

    Direction seule (base) :
    - Accélération constante : 90
    - Tendance à l'accélération : 70
    - Mixte : 55
    - Tendance à la décélération : 40
    - Décélération constante : 30

    Ajustement par le niveau absolu du dernier YoY :
    - Une accélération de -15% → -5% (encore négatif) ne mérite pas le même score
      qu'une accélération de +5% → +15% : réduction de 35%, plancher 20.
    - Une croissance quasi-nulle (< 3%) : légère pénalité de 15%, plancher 30.
    """
    if yoy_rates is None or len(yoy_rates) < 2:
        return 50.0

    # Calculer les deltas entre périodes successives
    deltas = [yoy_rates[i+1] - yoy_rates[i] for i in range(len(yoy_rates)-1)]

    # Nombre de périodes en accélération / décélération
    accelerating = sum(1 for d in deltas if d > 1.0)  # seuil 1% pour filtrer le bruit
    decelerating = sum(1 for d in deltas if d < -1.0)

    # Score de base (direction)
    if len(deltas) >= 2:
        # 3 points = 2 deltas
        if accelerating == len(deltas):
            base = 90.0  # Accélération constante
        elif decelerating == len(deltas):
            base = 30.0  # Décélération constante
        elif accelerating > decelerating:
            base = 70.0  # Tendance à l'accélération
        elif decelerating > accelerating:
            base = 40.0  # Tendance à la décélération
        else:
            base = 55.0  # Mixte
    else:
        # 2 points = 1 delta
        if deltas[0] > 2.0:
            base = 80.0  # En accélération
        elif deltas[0] < -2.0:
            base = 35.0  # En décélération
        else:
            base = 60.0  # Stable

    # Ajustement par le niveau absolu du dernier taux YoY
    last_yoy = yoy_rates[-1]
    if last_yoy < 0:
        # Croissance encore négative : "accélération" signifie moins pire, pas bon
        base = max(base * 0.65, 20.0)
    elif last_yoy < 3.0:
        # Croissance quasi nulle : légère pénalité
        base = max(base * 0.85, 30.0)

    return base


def compute_sma_score(price: Optional[float], sma_50: Optional[float], sma_200: Optional[float]) -> float:
    """
    Score basé sur la position du prix vs SMA50/SMA200.
    - Prix > SMA50 > SMA200 : tendance haussière forte (golden cross)
    - Prix > SMA200 mais < SMA50 : correction dans tendance haussière
    - Prix < SMA200 : tendance baissière
    - SMA50 < SMA200 : death cross
    """
    if price is None:
        return 50.0

    score = 50.0
    signals = 0

    # Prix vs SMA200 (signal long terme)
    if sma_200 is not None and sma_200 > 0:
        signals += 1
        pct_vs_200 = (price - sma_200) / sma_200 * 100
        if pct_vs_200 > 10:
            score += 15  # Bien au-dessus = forte tendance
        elif pct_vs_200 > 0:
            score += 10  # Au-dessus = tendance haussière
        elif pct_vs_200 > -10:
            score -= 10  # Légèrement en-dessous
        else:
            score -= 20  # Bien en-dessous = tendance baissière

    # Prix vs SMA50 (signal moyen terme)
    if sma_50 is not None and sma_50 > 0:
        signals += 1
        pct_vs_50 = (price - sma_50) / sma_50 * 100
        if pct_vs_50 > 5:
            score += 10
        elif pct_vs_50 > 0:
            score += 5
        elif pct_vs_50 > -5:
            score -= 5
        else:
            score -= 15

    # Golden Cross / Death Cross (SMA50 vs SMA200)
    if sma_50 is not None and sma_200 is not None and sma_200 > 0:
        signals += 1
        if sma_50 > sma_200:
            score += 10  # Golden cross = bullish
        else:
            score -= 10  # Death cross = bearish

    if signals == 0:
        return 50.0

    return max(0.0, min(100.0, score))


def compute_cash_conversion_score(fcf: Optional[float], net_income: Optional[float]) -> float:
    """
    Score de qualité des bénéfices basé sur le ratio FCF / Net Income.
    - Ratio > 1.2 : Excellente conversion (profits réels en cash)
    - Ratio 0.8-1.2 : Bonne qualité
    - Ratio 0.5-0.8 : Qualité moyenne
    - Ratio < 0.5 : Mauvaise qualité (profits comptables, peu de cash)
    - Net Income négatif + FCF positif : cas spécial (restructuration)
    """
    if fcf is None or net_income is None:
        return 50.0

    # Cas spécial : résultat négatif
    if net_income <= 0:
        if fcf > 0:
            return 65.0  # FCF positif malgré perte comptable = pas si mal
        else:
            return 25.0  # Perte + FCF négatif = problème

    ratio = fcf / net_income

    if ratio >= 1.5:
        return 90.0  # Cash massif vs bénéfices = très haute qualité
    elif ratio >= 1.2:
        return 80.0  # Excellente conversion
    elif ratio >= 0.8:
        return 70.0  # Bonne qualité
    elif ratio >= 0.5:
        return 50.0  # Qualité moyenne
    elif ratio >= 0.2:
        return 35.0  # Qualité faible
    else:
        return 20.0  # Profits comptables sans cash = drapeau rouge


def compute_analyst_score(
    current_price: Optional[float],
    target_mean: Optional[float],
    analyst_count: Optional[int],
    recommendation: Optional[str],
) -> float:
    """
    Score basé sur le consensus analystes.
    - Upside > 30% : très attractif
    - Upside 15-30% : attractif
    - Upside 5-15% : légèrement positif
    - Upside -5% à +5% : neutre
    - Downside > 5% : négatif
    - Downside > 15% : très négatif

    Pondéré par le nombre d'analystes (plus fiable si beaucoup d'analystes).
    Le recommendation key (buy/hold/sell) sert de signal complémentaire.
    """
    if current_price is None or target_mean is None or current_price <= 0:
        return 50.0

    # Score principal : upside/downside vs target
    upside_pct = (target_mean - current_price) / current_price * 100

    if upside_pct >= 40:
        price_score = 95.0
    elif upside_pct >= 25:
        price_score = 85.0
    elif upside_pct >= 15:
        price_score = 75.0
    elif upside_pct >= 5:
        price_score = 62.0
    elif upside_pct >= -5:
        price_score = 50.0  # Neutre
    elif upside_pct >= -15:
        price_score = 35.0
    elif upside_pct >= -25:
        price_score = 20.0
    else:
        price_score = 10.0

    # Score recommendation (signal complémentaire)
    # "outperform" et "strong_sell" sont des valeurs réelles retournées par Yahoo Finance
    # qui ne figuraient pas dans le mapping → tombaient sur le défaut neutre (50.0).
    reco_map = {
        "strong_buy":   90.0,
        "buy":          75.0,
        "outperform":   63.0,  # Entre buy et hold
        "hold":         50.0,
        "underperform": 30.0,
        "sell":         15.0,
        "strong_sell":   5.0,  # Plus négatif que sell
    }
    reco_score = reco_map.get(recommendation, 50.0) if recommendation else 50.0

    # Composite : 75% target price, 25% recommendation
    raw_score = 0.75 * price_score + 0.25 * reco_score

    # Facteur de fiabilité basé sur le nombre d'analystes
    # < 3 analystes : peu fiable, on rapproche le score de 50 (neutre)
    # >= 10 analystes : pleine confiance
    if analyst_count is not None and analyst_count > 0:
        reliability = clamp(analyst_count / 10.0, 0.3, 1.0)
    else:
        reliability = 0.3

    # Tirer le score vers 50 (neutre) quand peu d'analystes
    return 50.0 + (raw_score - 50.0) * reliability


def compute_macd_score(
    macd_line: Optional[float],
    macd_signal: Optional[float],
    macd_histogram: Optional[float],
    current_price: Optional[float],
) -> float:
    """
    Score basé sur le MACD (12, 26, 9).
    - MACD > Signal (histogramme positif) = momentum haussier
    - MACD < Signal (histogramme négatif) = momentum baissier
    - Croisement récent (histogramme proche de 0 et positif) = signal d'achat
    - Amplitude normalisée par le prix pour comparer entre actions

    Score orienté "opportunité d'achat" :
    - Histogramme positif croissant = fort momentum haussier
    - Histogramme négatif mais en réduction = retournement possible
    - Histogramme très négatif = momentum baissier
    """
    if macd_line is None or macd_signal is None or macd_histogram is None:
        return 50.0
    if current_price is None or current_price <= 0:
        return 50.0

    # Normaliser l'histogramme par le prix (en %)
    hist_pct = (macd_histogram / current_price) * 100

    # Score basé sur l'histogramme normalisé
    if hist_pct >= 1.0:
        score = 85.0   # Fort momentum haussier
    elif hist_pct >= 0.3:
        score = 72.0   # Momentum haussier
    elif hist_pct >= 0.05:
        score = 62.0   # Croisement haussier récent / léger momentum
    elif hist_pct >= -0.05:
        score = 50.0   # Neutre (croisement en cours)
    elif hist_pct >= -0.3:
        score = 38.0   # Légèrement baissier
    elif hist_pct >= -1.0:
        score = 28.0   # Momentum baissier
    else:
        score = 15.0   # Fort momentum baissier

    # Bonus/malus si MACD line elle-même est au-dessus/en-dessous de 0
    # MACD > 0 = tendance de fond haussière
    macd_pct = (macd_line / current_price) * 100
    if macd_pct > 0.5:
        score = min(100.0, score + 8)
    elif macd_pct < -0.5:
        score = max(0.0, score - 8)

    return score


def compute_price_to_ocf_score(p_ocf: Optional[float]) -> float:
    """
    Score basé sur le ratio Price / Operating Cash Flow (P/OCF).

    L'OCF est le cash généré avant déduction du capex. Pour les secteurs
    capitalistiques (utilities, industriels, télécoms, immobilier), où le capex
    est élevé mais obligatoire pour maintenir l'activité, l'OCF reflète mieux
    la capacité bénéficiaire réelle que le FCF. Ce ratio complète le FCF yield
    en évitant la double-pénalisation des industries capital-intensives.

    Un P/OCF négatif (OCF négatif) = entreprise en difficulté de trésorerie → exclu.

    - < 5   : Exceptionnellement bon marché → 95
    - 5–10  : Très attractif → 85
    - 10–15 : Attractif → 72
    - 15–20 : Fair value → 58
    - 20–30 : Légèrement cher → 40
    - 30–50 : Cher → 22
    - > 50  : Très cher → 8
    """
    if p_ocf is None:
        return 50.0
    if p_ocf <= 0:
        return 10.0   # OCF négatif — situation tendue
    if p_ocf < 5:
        return 95.0
    if p_ocf < 10:
        return 85.0
    if p_ocf < 15:
        return 72.0
    if p_ocf < 20:
        return 58.0
    if p_ocf < 30:
        return 40.0
    if p_ocf < 50:
        return 22.0
    return 8.0


def compute_pb_score_sector_aware(pb: Optional[float], sector: Optional[str], industry: Optional[str]) -> float:
    """
    Score P/B ajusté par secteur et industrie.

    Certains business modèles ont naturellement un P/B très élevé
    (concessions, tech/SaaS, services) car ils ont peu d'actifs tangibles
    au bilan mais une forte capacité bénéficiaire. Pénaliser ces secteurs
    sur le P/B n'a pas de sens.

    Approche :
    - Pour les secteurs "asset-light", on réduit le poids du P/B en
      rapprochant le score vers 50 (neutre) au lieu de 0.
    - Pour les secteurs "asset-heavy" (banques, utilities, industriels lourds),
      le P/B reste un critère important.
    """
    if pb is None:
        return 50.0

    # Industries / secteurs où le P/B est structurellement élevé et non pertinent
    asset_light_industries = {
        "airports & air services", "software", "internet content & information",
        "semiconductors", "entertainment", "media", "advertising agencies",
        "consulting services", "staffing & employment services",
        "specialty business services", "information technology services",
        "health information services", "financial data & stock exchanges",
        "credit services", "asset management",
    }

    asset_light_sectors = {"Technology", "Communication Services"}

    industry_lower = (industry or "").lower()
    is_asset_light = (
        industry_lower in asset_light_industries
        or sector in asset_light_sectors
    )

    # Score brut P/B (logique standard)
    raw_score = score_linear_inverse(pb, lo=1.0, hi=8.0)

    if is_asset_light:
        # Pour les asset-light : on neutralise le P/B en tirant vers 50
        # Le P/B a peu de signification pour ces business
        return 50.0 + (raw_score - 50.0) * 0.2  # 80% neutralisé
    else:
        return raw_score


def compute_interest_coverage_score(interest_coverage: Optional[float]) -> float:
    """
    Score basé sur Interest Coverage = EBIT / Interest Expense.
    - > 10x : Excellente couverture
    - 5-10x : Bonne couverture
    - 3-5x : Adéquate
    - 2-3x : Faible
    - < 2x : Danger
    """
    if interest_coverage is None:
        return 50.0
    if interest_coverage >= 15:
        return 90.0
    elif interest_coverage >= 10:
        return 80.0
    elif interest_coverage >= 5:
        return 70.0
    elif interest_coverage >= 3:
        return 55.0
    elif interest_coverage >= 2:
        return 35.0
    elif interest_coverage >= 1:
        return 20.0
    else:
        return 10.0  # EBIT ne couvre pas les intérêts


def compute_share_dilution_score(dilution_pct: Optional[float]) -> float:
    """
    Score basé sur la dilution des actionnaires sur 3 ans (en %).
    - Négatif (rachat d'actions) = très positif
    - 0-3% = neutre
    - 3-10% = dilution modérée
    - > 10% = forte dilution
    """
    if dilution_pct is None:
        return 50.0
    if dilution_pct <= -5:
        return 90.0  # Rachat massif d'actions
    elif dilution_pct <= -2:
        return 80.0  # Rachat significatif
    elif dilution_pct <= 0:
        return 70.0  # Léger rachat ou stable
    elif dilution_pct <= 3:
        return 55.0  # Dilution minime
    elif dilution_pct <= 7:
        return 40.0  # Dilution modérée
    elif dilution_pct <= 15:
        return 25.0  # Forte dilution
    else:
        return 10.0  # Dilution massive


def compute_volatility_score(volatility_pct: Optional[float]) -> float:
    """
    Score basé sur la volatilité annualisée (en %).
    Volatilité basse = plus prévisible = meilleur score.
    """
    if volatility_pct is None:
        return 50.0
    if volatility_pct <= 15:
        return 85.0  # Très stable
    elif volatility_pct <= 25:
        return 70.0  # Stable
    elif volatility_pct <= 35:
        return 55.0  # Moyenne
    elif volatility_pct <= 50:
        return 35.0  # Volatile
    else:
        return 15.0  # Très volatile


# ---------------------------------------------------------------------------
# Scoring CAGR du CA ajusté par secteur
# Un CAGR de 15% est exceptionnel pour une utility (norme ~2-4%) mais ordinaire
# pour une tech SaaS (norme ~15-25%). La plage fixe (0-25%) appliquée à tous les
# secteurs pénalise injustement les secteurs matures à croissance structurellement
# basse (utilities, staples, énergie) et sous-score les secteurs à forte croissance
# (tech, financial services fintech) où 15% est une performance dans la moyenne.
# ---------------------------------------------------------------------------

_SECTOR_CAGR_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (5.0,  30.0),  # Croissance attendue élevée
    "Communication Services":  (3.0,  20.0),
    "Consumer Discretionary":  (3.0,  18.0),
    "Health Care":             (5.0,  22.0),  # Pharma/biotech : pipelines à forte valeur
    "Industrials":             (2.0,  15.0),
    "Consumer Staples":        (1.0,  10.0),  # Marché mature, croissance structurellement basse
    "Materials":               (1.0,  12.0),
    "Energy":                  (0.0,  12.0),  # Très cyclique
    "Real Estate":             (1.0,   8.0),  # REITs : régulés, croissance limitée
    "Utilities":               (0.0,   6.0),  # Marché régulé, croissance quasi-nulle = normal
    "Financials":              (2.0,  12.0),
    "Financial Services":      (5.0,  25.0),  # Fintech/néo-banques : forte croissance attendue
}
_DEFAULT_CAGR_RANGE: tuple[float, float] = (0.0, 25.0)


def compute_cagr_score_sector_aware(cagr: Optional[float], sector: Optional[str]) -> float:
    """
    Score CAGR CA calibré selon le secteur.

    La croissance du chiffre d'affaires est interprétée différemment selon le contexte :
    - Une utility à +6% CAGR surperforme structurellement son secteur → score élevé.
    - Une tech à +6% CAGR est en sous-performance → score bas.

    - cagr is None → 50 (neutre)
    - cagr < 0     →  0 (contraction du CA — signal négatif absolu)
    """
    if cagr is None:
        return 50.0
    if cagr < 0:
        return 0.0  # Contraction du CA = toujours mauvais, quel que soit le secteur
    lo, hi = _SECTOR_CAGR_RANGES.get(sector or "", _DEFAULT_CAGR_RANGE)
    return score_linear(cagr, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Scoring marge EBIT ajustée par secteur
# La marge EBIT varie structurellement selon les secteurs : un retailer à 4%
# EBIT est dans la norme de son secteur (Walmart ~4-5%), mais avec la plage
# fixe (5-30%) il obtiendrait 0/100 — pénalisation injuste. À l'inverse,
# une tech SaaS à 5% EBIT serait perçue comme "correcte" alors qu'elle est
# en sous-performance pour son secteur (norme 15-35%).
# ---------------------------------------------------------------------------

_SECTOR_EBIT_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (10.0, 35.0),  # SaaS/logiciels : marges élevées attendues
    "Communication Services":  (8.0,  30.0),
    "Consumer Discretionary":  (4.0,  18.0),  # Retail discrétionnaire
    "Health Care":             (8.0,  30.0),  # Pharma / medical devices
    "Industrials":             (5.0,  20.0),
    "Consumer Staples":        (3.0,  15.0),  # Grocery, FMCG : marges structurellement basses
    "Materials":               (5.0,  20.0),
    "Energy":                  (5.0,  22.0),  # Cyclique mais capex important
    "Real Estate":             (15.0, 45.0),  # REITs : marges opérationnelles élevées
    "Utilities":               (8.0,  22.0),  # Revenus régulés, marges stables
    # Financials / Financial Services : exclus via is_financial → neutralisés à 50
}
_DEFAULT_EBIT_RANGE: tuple[float, float] = (5.0, 30.0)


def compute_ebit_score_sector_aware(ebit_margin: Optional[float], sector: Optional[str]) -> float:
    """
    Score marge EBIT calibré selon le secteur.

    La marge EBIT est interprétée en relatif par rapport aux normes du secteur :
    - Un retailer (Consumer Staples) à 4% EBIT est performant pour son secteur.
    - Une tech à 4% EBIT est en sous-performance sévère.

    - ebit_margin is None → 50 (neutre)
    """
    if ebit_margin is None:
        return 50.0
    lo, hi = _SECTOR_EBIT_RANGES.get(sector or "", _DEFAULT_EBIT_RANGE)
    return score_linear(ebit_margin, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Scoring marge brute (Gross Margin) ajusté par secteur
# La marge brute varie structurellement selon les secteurs :
# - Software/SaaS : >70% normal (coûts de livraison quasi-nuls)
# - Retail/Distribution : 20-35% typique (coût des marchandises élevé)
# - Energie/Matières premières : 20-40% selon les cycles de commodités
# Un retailer à 28% de marge brute est sain ; une tech SaaS à 28% est en difficulté.
# ---------------------------------------------------------------------------

_SECTOR_GROSS_MARGIN_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (50.0, 80.0),  # SaaS/logiciels : coûts variables très faibles
    "Communication Services":  (40.0, 70.0),  # Médias, télécoms
    "Consumer Discretionary":  (25.0, 50.0),  # Retail discrétionnaire, e-commerce
    "Health Care":             (40.0, 70.0),  # Pharma : marges élevées post-R&D
    "Industrials":             (20.0, 45.0),  # Manufacturing
    "Consumer Staples":        (20.0, 45.0),  # Grocery, FMCG : prix comprimés
    "Materials":               (15.0, 40.0),  # Matières premières, chimie
    "Energy":                  (15.0, 40.0),  # Cyclique, coûts d'extraction élevés
    "Real Estate":             (40.0, 70.0),  # Revenus locatifs à forte marge
    "Utilities":               (25.0, 50.0),  # Coûts de production régulés
    "Financial Services":      (50.0, 80.0),  # Commissions / spread (exchanges, etc.)
    "Financials":              (50.0, 80.0),
}
_DEFAULT_GROSS_MARGIN_RANGE: tuple[float, float] = (20.0, 60.0)


def compute_gross_margin_score_sector_aware(gross_margin: Optional[float], sector: Optional[str]) -> float:
    """
    Score marge brute calibré selon le secteur.
    gross_margin is None → 50 (neutre)
    """
    if gross_margin is None:
        return 50.0
    lo, hi = _SECTOR_GROSS_MARGIN_RANGES.get(sector or "", _DEFAULT_GROSS_MARGIN_RANGE)
    return score_linear(gross_margin, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# AMÉLIORATION 2 : Scoring ROE ajusté par secteur
# Le ROE est distordu par le levier financier et varie structurellement selon
# les secteurs. Un ROE de 15% est excellent pour une banque mais médiocre pour
# une entreprise tech qui génère peu d'actifs tangibles.
# ---------------------------------------------------------------------------

_SECTOR_ROE_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (10.0, 35.0),
    "Communication Services":  (10.0, 30.0),
    "Consumer Discretionary":  (10.0, 30.0),
    "Health Care":             (10.0, 30.0),
    "Industrials":             (8.0,  25.0),
    "Consumer Staples":        (10.0, 25.0),
    "Materials":               (8.0,  22.0),
    "Energy":                  (8.0,  20.0),
    "Real Estate":             (4.0,  14.0),  # REIT : ROE naturellement plus faible
    "Utilities":               (6.0,  16.0),
    "Financials":              (8.0,  18.0),  # Banques : 12-15% = excellent
    "Financial Services":      (8.0,  18.0),
}
_DEFAULT_ROE_RANGE: tuple[float, float] = (5.0, 25.0)


def compute_roe_score_sector_aware(roe: Optional[float], sector: Optional[str]) -> float:
    """
    Score ROE calibré selon le secteur.

    Le ROE est mécaniquement amplifié par le levier (ROE = Net Income / Equity).
    Une banque avec 10x de levier sur ses actifs peut afficher un ROE de 15%
    avec un ROA de seulement 1.5% — ce qui est en réalité une bonne performance.
    Utiliser le même référentiel pour toutes les industries défavorise injustement
    les secteurs à forte intensité capitalistique (utilities, REITs) et avantage
    les secteurs asset-light (tech, SaaS).

    - roe is None → 50 (neutre)
    - roe <= 0    → 10 (pertes pour les actionnaires)
    """
    if roe is None:
        return 50.0
    if roe <= 0:
        return 10.0  # ROE négatif = pertes nettes pour les actionnaires
    lo, hi = _SECTOR_ROE_RANGES.get(sector or "", _DEFAULT_ROE_RANGE)
    return score_linear(roe, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Scoring EV/Sales ajusté par secteur
# EV/Sales (Enterprise Value / Chiffre d'affaires) est particulièrement utile
# pour les sociétés sans EBITDA positif (croissance, BNPL, SaaS early-stage).
# Mais les niveaux normaux varient énormément selon le secteur :
# - Une tech SaaS à 12x EV/Sales est en "fair value" (business model hautement scalable)
# - Une utility à 12x EV/Sales est hors-marché (revenus régulés, peu de marge)
# La plage fixe (2-10x) pénalisait injustement les secteurs à marge élevée.
# ---------------------------------------------------------------------------

_SECTOR_EV_SALES_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (3.0,  15.0),  # SaaS/tech : premium valorisé
    "Communication Services":  (2.0,  10.0),
    "Consumer Discretionary":  (0.5,   5.0),
    "Health Care":             (2.0,  10.0),  # Biotech/pharma : pipelines valorisés
    "Industrials":             (0.5,   3.0),
    "Consumer Staples":        (0.5,   2.5),
    "Materials":               (0.5,   2.5),
    "Energy":                  (0.5,   2.0),
    "Real Estate":             (2.0,   8.0),
    "Utilities":               (1.0,   3.5),
    "Financials":              (1.5,   6.0),
    "Financial Services":      (2.0,  12.0),  # Fintech/BNPL : premium de croissance (Klarna, Affirm jusqu'à ~10x)
}
_DEFAULT_EV_SALES_RANGE: tuple[float, float] = (2.0, 10.0)


def compute_ev_sales_score_sector_aware(
    ev_sales: Optional[float], sector: Optional[str]
) -> float:
    """
    Score EV/Sales inversé, calibré selon le secteur.

    EV/Sales est crucial pour scorer les sociétés à EBITDA négatif (croissance,
    BNPL, SaaS early-stage). Klarna/Affirm à 6-10x EV/Sales n'est pas cher pour
    le segment — mais avec la plage fixe (2-10x), elles scoraient quasi 0.

    - ev_sales is None → 50 (neutre)
    - ev_sales <= 0   →  0 (CA nul ou négatif — cas extrême)
    """
    if ev_sales is None:
        return 50.0
    if ev_sales <= 0:
        return 0.0
    lo, hi = _SECTOR_EV_SALES_RANGES.get(sector or "", _DEFAULT_EV_SALES_RANGE)
    return score_linear_inverse(ev_sales, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Scoring EV/EBITDA ajusté par secteur
# EV/EBITDA varie structurellement selon les secteurs : une tech à 30x est en
# "fair value" historique alors qu'une société énergétique à 30x est hors-marché.
# Utiliser une plage fixe (8-25x) pénalise injustement les secteurs à croissance
# élevée (tech, santé) et avantage les secteurs cycliques (énergie, matériaux).
# ---------------------------------------------------------------------------

_SECTOR_EV_EBITDA_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (15.0, 40.0),
    "Communication Services":  (10.0, 35.0),
    "Consumer Discretionary":  (8.0,  25.0),
    "Health Care":             (12.0, 30.0),
    "Industrials":             (8.0,  20.0),
    "Consumer Staples":        (10.0, 22.0),
    "Materials":               (6.0,  15.0),
    "Energy":                  (4.0,  12.0),
    "Real Estate":             (15.0, 32.0),  # REITs : multiples structurellement élevés
    "Utilities":               (8.0,  18.0),
    # Financials/Financial Services : EV/EBITDA non pertinent (géré par is_financial)
}
_DEFAULT_EV_EBITDA_RANGE: tuple[float, float] = (8.0, 25.0)


def compute_ev_ebitda_score_sector_aware(
    ev_ebitda: Optional[float], sector: Optional[str]
) -> float:
    """
    Score EV/EBITDA inversé, calibré selon le secteur.

    EV/EBITDA est le multiple d'acquisition de référence. Mais chaque secteur
    a des niveaux historiques très différents reflétant la croissance attendue,
    le capex, et le risque de cycle.

    - ev_ebitda is None  → 50 (neutre)
    - ev_ebitda <= 0     →  0 (EBITDA négatif = pertes opérationnelles)
    """
    if ev_ebitda is None:
        return 50.0
    if ev_ebitda <= 0:
        return 0.0
    lo, hi = _SECTOR_EV_EBITDA_RANGES.get(sector or "", _DEFAULT_EV_EBITDA_RANGE)
    return score_linear_inverse(ev_ebitda, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Scoring P/E ajusté par secteur
# Chaque secteur a des niveaux de valorisation historiques différents.
# ---------------------------------------------------------------------------

_SECTOR_PE_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (15.0, 50.0),
    "Communication Services":  (15.0, 45.0),
    "Consumer Discretionary":  (12.0, 38.0),
    "Health Care":             (15.0, 40.0),
    "Industrials":             (12.0, 35.0),
    "Consumer Staples":        (14.0, 30.0),
    "Materials":               (10.0, 28.0),
    "Energy":                  (8.0,  25.0),
    "Real Estate":             (20.0, 60.0),
    "Utilities":               (12.0, 25.0),
    "Financials":              (7.0,  18.0),   # Banques traditionnelles (nomenclature MSCI/S&P)
    # Yahoo Finance utilise "Financial Services" pour les banques, fintech, assurance.
    # Les fintech/néo-banques à forte croissance (SOFI, NU, AFRM...) se négocient
    # structurellement à des P/E plus élevés que les banques traditionnelles.
    # Range élargi pour refléter les niveaux de valorisation growth de ce sous-secteur.
    "Financial Services":      (12.0, 45.0),
}
_DEFAULT_PE_RANGE: tuple[float, float] = (10.0, 40.0)


def compute_pe_score_sector_aware(pe: Optional[float], sector: Optional[str]) -> float:
    """
    Score P/E inversé, calibré selon le secteur.

    Chaque secteur a des bornes (lo, hi) reflétant ses niveaux de valorisation
    historiques habituels. Un P/E de 30 est cheap en Tech mais cher en Énergie.

    - pe <= 0  → 0 (entreprise en perte = signal négatif fort)
    - pe is None → 50 (neutre)
    """
    if pe is None:
        return 50.0
    if pe <= 0:
        return 0.0  # Perte nette
    lo, hi = _SECTOR_PE_RANGES.get(sector or "", _DEFAULT_PE_RANGE)
    return score_linear_inverse(pe, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Amélioration 1 : score unitaire d'un retour de prix (utilisé pour le momentum
# multi-timeframe dans compute_potential_score)
# ---------------------------------------------------------------------------

def compute_short_interest_score(short_pct: Optional[float]) -> float:
    """
    Score basé sur le Short Interest (% du float vendu à découvert).

    Un taux élevé signifie que beaucoup de traders parient sur une baisse —
    c'est un signal de risque accru. Traité comme un indicateur de risque inversé
    (plus le short interest est fort, plus le score est pénalisé).

    Cas extrême > 20% : possible short squeeze, mais risque très élevé.
    On ne récompense pas le potentiel de squeeze — trop spéculatif.

    - < 1%   : Quasi-aucun court-vendeur → très sain
    - 1-3%   : Normal / faible pression
    - 3-7%   : Modéré — quelques bears présents
    - 7-15%  : Élevé — pression baissière significative
    - 15-25% : Très élevé — forte conviction baissière du marché
    - > 25%  : Extrême — risque majeur ou quasi-faillite anticipée
    """
    if short_pct is None:
        return 50.0
    if short_pct < 1:
        return 88.0   # Presque pas de short sellers
    if short_pct < 3:
        return 75.0   # Faible — normal
    if short_pct < 7:
        return 58.0   # Modéré
    if short_pct < 15:
        return 38.0   # Élevé — signal négatif
    if short_pct < 25:
        return 20.0   # Très élevé — forte conviction baissière
    return 8.0        # Extrême — risque majeur


def compute_insider_ownership_score(insider_pct: Optional[float]) -> float:
    """
    Score basé sur le % d'actions détenues par les insiders (dirigeants, fondateurs).

    Principe : plus les insiders détiennent d'actions, plus leurs intérêts
    sont alignés avec ceux des actionnaires extérieurs (ils perdent si l'action baisse).

    - < 1%   : Management presque pas investi → peu d'alignement
    - 1-5%   : Faible mais présent
    - 5-15%  : Modéré — engagement visible
    - 15-30% : Fort — management très investi
    - 30-60% : Très fort — souvent fondateur encore présent
    - > 60%  : Très concentré (alignement maximal, mais risque de liquidité réduite)
    """
    if insider_pct is None:
        return 50.0
    if insider_pct < 1:
        return 20.0   # Quasi-aucun intérêt personnel
    if insider_pct < 5:
        return 40.0   # Faible
    if insider_pct < 15:
        return 62.0   # Modéré
    if insider_pct < 30:
        return 78.0   # Fort
    if insider_pct < 60:
        return 88.0   # Très fort (fondateur souvent)
    return 78.0       # > 60% : alignement max mais float réduit


def compute_net_margin_score(net_margin: Optional[float]) -> float:
    """
    Score basé sur la marge nette (Net Income / Revenue, en %).

    Complète l'EBIT margin en montrant ce qu'il reste réellement aux actionnaires
    après impôts ET charges financières. Une EBIT margin élevée avec une net margin
    faible révèle une structure financière coûteuse (dette lourde ou fiscalité élevée).

    Seuils :
    - < 0%   : Perte nette (après tout)
    - 0-3%   : Très mince (industrie, retail bas de gamme)
    - 3-7%   : Modeste mais viable
    - 7-12%  : Bonne rentabilité
    - 12-20% : Très bonne (business model solide)
    - > 20%  : Excellente (pricing power fort ou actif léger)
    """
    if net_margin is None:
        return 50.0
    if net_margin <= 0:
        return 12.0   # Perte nette après tout
    if net_margin <= 3:
        return 28.0   # Très mince
    if net_margin <= 7:
        return 48.0   # Modeste
    if net_margin <= 12:
        return 65.0   # Bonne
    if net_margin <= 20:
        return 80.0   # Très bonne
    return 92.0       # > 20% = forte capacité bénéficiaire


def compute_eps_growth_score(eps_growth: Optional[float]) -> float:
    """
    Score basé sur la croissance du BPA (Earnings Per Share) YoY en %.

    Complète le Revenue CAGR : une entreprise peut faire croître ses revenus
    tout en voyant ses bénéfices stagner ou baisser (expansion des coûts,
    dilution, hausse des intérêts). L'EPS Growth détecte ce découplage.

    - < -30% : Effondrement des bénéfices
    - -30% à -10% : Forte baisse
    - -10% à  0%  : Légère baisse
    -   0% à 10%  : Croissance modeste
    -  10% à 25%  : Bonne croissance
    -  25% à 50%  : Forte croissance
    -  > 50%      : Exceptionnel (attention aux effets de base)
    """
    if eps_growth is None:
        return 50.0
    if eps_growth <= -30:
        return 8.0    # Effondrement
    if eps_growth <= -10:
        return 22.0   # Forte contraction
    if eps_growth <= 0:
        return 38.0   # Légère contraction
    if eps_growth <= 10:
        return 55.0   # Croissance modeste
    if eps_growth <= 25:
        return 72.0   # Bonne croissance
    if eps_growth <= 50:
        return 85.0   # Forte croissance
    return 78.0       # > 50% : probable effet de base, légèrement pénalisé


def compute_current_ratio_score(current_ratio: Optional[float]) -> float:
    """
    Score basé sur le Current Ratio = Actifs court terme / Passifs court terme.

    Mesure la capacité à honorer les dettes à court terme.
    Complète le Net Debt/EBITDA (solvabilité long terme) avec la liquidité immédiate.

    - < 0.5 : Crise de liquidité (risque de défaut imminent)
    - 0.5-0.8 : Liquidité insuffisante
    - 0.8-1.0 : Tendu, peu de marge
    - 1.0-1.5 : Acceptable
    - 1.5-2.5 : Confortable (zone idéale)
    - > 2.5   : Très liquide (trésorerie abondante)

    Note : un ratio > 4 peut indiquer du cash idle mal déployé,
    mais reste préférable à un ratio < 1.
    """
    if current_ratio is None:
        return 50.0
    if current_ratio < 0.5:
        return 8.0    # Quasi-insolvable à court terme
    elif current_ratio < 0.8:
        return 22.0   # Insuffisant
    elif current_ratio < 1.0:
        return 38.0   # Tendu
    elif current_ratio < 1.5:
        return 58.0   # Acceptable
    elif current_ratio < 2.0:
        return 75.0   # Bon
    elif current_ratio < 2.5:
        return 85.0   # Très bon
    elif current_ratio < 4.0:
        return 90.0   # Excellente liquidité
    else:
        return 82.0   # Cash très élevé (légèrement sous-optimal mais pas risqué)


def compute_roic_score(roic: Optional[float]) -> float:
    """
    Score basé sur le ROIC (Return on Invested Capital / ROA).

    Mesure l'efficacité avec laquelle l'entreprise utilise son capital total
    (equity + dette) pour générer du profit. Contrairement au ROE, il n'est
    pas biaisé par le levier financier.

    Seuils :
    - ≤ 0%  : Actifs non rentables (perte)          → score faible
    - 1-5%  : Rendement insuffisant                 → 25-45
    - 5-10% : Correct                               → 50-65
    - 10-15%: Bon                                   → 70-80
    - 15-20%: Très bon                              → 82-90
    - > 20% : Excellent (wide moat probable)        → 92-98
    """
    if roic is None:
        return 50.0
    if roic <= 0:
        return 15.0  # Actifs générant des pertes
    if roic <= 3:
        return 30.0
    if roic <= 6:
        return 48.0
    if roic <= 10:
        return 63.0
    if roic <= 15:
        return 78.0
    if roic <= 20:
        return 88.0
    return 96.0  # ROIC > 20% = avantage compétitif fort


def compute_institutional_ownership_score(inst_pct: Optional[float]) -> float:
    """
    Score basé sur le % d'actions détenues par les investisseurs institutionnels.

    Les institutionnels (fonds de pension, hedge funds, assureurs, mutual funds)
    font une due diligence approfondie avant d'investir. Un taux élevé signifie
    que le "smart money" a confiance dans le titre. Mais une concentration excessive
    crée un risque de vente en bloc lors de rachats massifs.

    - < 5%   : Quasi-ignoré des institutionnels → peu de validation externe
    - 5-20%  : Faible présence institutionnelle
    - 20-40% : Présence modérée — intérêt croissant
    - 40-60% : Bonne couverture institutionnelle (zone idéale)
    - 60-80% : Forte présence — haut niveau de confiance
    - > 80%  : Très concentré — risque de pression vendeuse coordonnée
    """
    if inst_pct is None:
        return 50.0
    if inst_pct < 5:
        return 20.0   # Ignoré des institutionnels — peu de validation
    if inst_pct < 20:
        return 38.0   # Faible présence
    if inst_pct < 40:
        return 58.0   # Présence modérée
    if inst_pct < 60:
        return 75.0   # Bonne couverture (zone idéale)
    if inst_pct < 80:
        return 85.0   # Forte confiance institutionnelle
    return 70.0       # > 80% : risque de vente en bloc coordonnée


def compute_accruals_score(accruals_ratio: Optional[float]) -> float:
    """
    Score basé sur l'Accruals Ratio (anomalie de Sloan, 1996).
    Formula : (Net Income − Operating Cash Flow) / Total Assets × 100

    Un ratio BAS ou NÉGATIF = bénéfices couverts par du cash réel → haute qualité.
    Un ratio ÉLEVÉ = bénéfices supérieurs aux flux de cash → ajustements comptables
    suspects ou timing décalé → signal d'alerte (risque de déception future).

    Les portefeuilles "low accruals" surperforment systématiquement les "high accruals".
    """
    if accruals_ratio is None:
        return 50.0
    if accruals_ratio < -10:
        return 92.0   # Cash très supérieur aux bénéfices déclarés
    if accruals_ratio < -3:
        return 80.0   # Très haute qualité des bénéfices
    if accruals_ratio < 0:
        return 68.0   # Bonne qualité
    if accruals_ratio < 3:
        return 55.0   # Acceptable
    if accruals_ratio < 7:
        return 38.0   # Accruals significatifs — prudence
    if accruals_ratio < 12:
        return 22.0   # Drapeau rouge
    return 8.0        # Alarme — potentielle inflation des bénéfices


def compute_gross_margin_trend_score(trend: Optional[float]) -> float:
    """
    Score basé sur la variation de la marge brute sur 2 ans (en points de %).

    Un trend positif = pricing power ou maîtrise des coûts (qualité en hausse).
    Un trend négatif = compression des marges = signal d'alerte.

    - <= -8 pp : Fort effondrement de la marge
    - -4 à -8  : Contraction significative
    - -1 à -4  : Légère contraction
    - -1 à +1  : Stable (neutre)
    - +1 à +4  : Légère expansion
    - +4 à +8  : Bonne expansion
    - > +8 pp  : Forte expansion (pricing power marqué)
    """
    if trend is None:
        return 50.0
    if trend <= -8:
        return 10.0   # Effondrement de la marge
    if trend <= -4:
        return 25.0   # Contraction significative
    if trend <= -1:
        return 42.0   # Légère contraction
    if trend <= 1:
        return 58.0   # Stable
    if trend <= 4:
        return 72.0   # Légère expansion
    if trend <= 8:
        return 85.0   # Bonne expansion
    return 95.0       # Forte expansion (> +8 pp) = pricing power marqué


def compute_relative_momentum_score(rel_mom: Optional[float]) -> float:
    """
    Score basé sur la performance du titre RELATIVE à l'ETF de son secteur.
    rel_mom = stock_return − sector_ETF_return (en %)

    Un rel_mom positif = surperformance vs secteur → signal momentum qualifié.
    Un rel_mom négatif = sous-performance → faiblesse relative même si prix monte.

    Cette métrique est orthogonale au momentum absolu : un titre peut avoir
    un momentum absolu fort mais un momentum relatif faible (secteur en feu)
    ou vice versa (titre solide dans un secteur en difficulté).
    """
    if rel_mom is None:
        return 50.0
    if rel_mom >= 25:
        return 92.0   # Surperformance massive vs secteur
    if rel_mom >= 15:
        return 82.0   # Forte surperformance
    if rel_mom >= 8:
        return 72.0   # Bonne surperformance
    if rel_mom >= 3:
        return 62.0   # Légère surperformance
    if rel_mom >= -3:
        return 52.0   # Dans la moyenne du secteur
    if rel_mom >= -8:
        return 40.0   # Légère sous-performance
    if rel_mom >= -15:
        return 28.0   # Sous-performance significative
    if rel_mom >= -25:
        return 18.0   # Forte sous-performance
    return 8.0        # Sous-performance massive vs secteur


def _score_single_momentum(m: Optional[float]) -> float:
    """Score non-linéaire d'un retour de prix (%) ; pénalise les extrêmes."""
    if m is None:
        return 50.0
    if m <= -30:
        return 10.0   # Effondrement
    if m <= -15:
        return 25.0   # Forte baisse
    if m <= -5:
        return 40.0   # Baisse modérée
    if m <= 5:
        return 55.0   # Stable / léger
    if m <= 15:
        return 72.0   # Bonne performance
    if m <= 30:
        return 85.0   # Forte performance
    if m <= 50:
        return 78.0   # Très forte perf — début de surchauffe
    return 60.0       # Momentum extrême = risque de correction


def compute_altman_z_score(z: Optional[float]) -> float:
    """
    Score basé sur l'Altman Z-Score (prédiction de détresse financière, 1968).

    Z = 1.2·(WC/TA) + 1.4·(RE/TA) + 3.3·(EBIT/TA) + 0.6·(Mcap/Debt) + 1.0·(Rev/TA)

    Zones originales :
    - Z < 1.81  : Zone de détresse — forte probabilité de faillite dans les 2 ans
    - 1.81–2.99 : Zone grise — situation ambiguë, surveiller
    - Z ≥ 2.99  : Zone saine — risque de faillite faible

    Plus le Z est élevé, plus la santé financière est solide.
    Indicateur robuste pour les entreprises industrielles ; à pondérer avec prudence
    pour les banques (bilan structurellement différent) et les pure-tech sans actifs.
    """
    if z is None:
        return 50.0
    if z < 1.23:
        return 8.0    # Détresse sévère — faillite probable
    if z < 1.81:
        return 22.0   # Zone de détresse
    if z < 2.30:
        return 38.0   # Zone grise basse
    if z < 2.99:
        return 52.0   # Zone grise haute — ambiguë
    if z < 4.00:
        return 70.0   # Zone saine — faible risque
    if z < 6.00:
        return 83.0   # Bonne santé financière
    return 92.0       # Excellente solidité financière


def compute_drawdown_score(max_drawdown_pct: Optional[float]) -> float:
    """
    Score basé sur le max drawdown 1Y (en %, valeur négative).
    Drawdown faible = meilleur score.
    """
    if max_drawdown_pct is None:
        return 50.0
    dd = abs(max_drawdown_pct)  # Travailler en valeur absolue
    if dd <= 10:
        return 85.0  # Faible drawdown
    elif dd <= 20:
        return 70.0  # Modéré
    elif dd <= 30:
        return 55.0  # Significatif
    elif dd <= 40:
        return 35.0  # Important
    elif dd <= 50:
        return 20.0  # Sévère
    else:
        return 10.0  # Crash


# ---------------------------------------------------------------------------
# Amélioration 1 : FCF yield ajusté par secteur
# Un FCF yield de 4% est excellent pour une tech SaaS (réinvestissement fort attendu)
# mais insuffisant pour une société énergétique cyclique (risque de cycle élevé justifie
# une prime de rendement). La plage fixe (1-8%) favorisait injustement les secteurs
# à faible croissance et pénalisait les tech SaaS à fort réinvestissement.
# ---------------------------------------------------------------------------

_SECTOR_FCF_YIELD_RANGES: dict[str, tuple[float, float]] = {
    "Technology":              (1.5, 6.0),   # SaaS/logiciels : réinvestissement fort, FCF modéré attendu
    "Communication Services":  (2.0, 7.0),
    "Consumer Discretionary":  (2.0, 8.0),
    "Health Care":             (2.0, 7.0),
    "Industrials":             (2.5, 8.0),
    "Consumer Staples":        (3.0, 8.0),
    "Materials":               (3.0, 10.0),  # Cyclique : FCF yield élevé au pic de cycle
    "Energy":                  (4.0, 15.0),  # Très cyclique, FCF yield élevé attendu
    "Real Estate":             (2.0, 6.0),   # REITs : capex élevé, FCF yield modéré
    "Utilities":               (2.5, 6.0),   # Régulé, FCF yield stable et modéré
    "Financials":              (2.0, 8.0),
    "Financial Services":      (2.0, 8.0),
}
_DEFAULT_FCF_YIELD_RANGE: tuple[float, float] = (1.0, 8.0)


def compute_fcf_yield_score_sector_aware(fcf_yield: Optional[float], sector: Optional[str]) -> float:
    """
    Score FCF yield calibré selon le secteur.

    Chaque secteur a des niveaux de FCF yield structurellement différents reflétant
    le cycle de vie (réinvestissement vs maturité), le capex obligatoire et le risque.

    - fcf_yield is None → 50 (neutre)
    - fcf_yield <= 0   → 10 (FCF négatif — signal négatif mais non rédhibitoire
                             pour une entreprise en forte phase de croissance)
    """
    if fcf_yield is None:
        return 50.0
    if fcf_yield <= 0:
        return 10.0
    lo, hi = _SECTOR_FCF_YIELD_RANGES.get(sector or "", _DEFAULT_FCF_YIELD_RANGE)
    return score_linear(fcf_yield, lo=lo, hi=hi)


# ---------------------------------------------------------------------------
# Amélioration 2 : Momentum quality score (Sharpe-like simplifié)
# Un gain de +30% avec 15% de volatilité est un signal très différent d'un gain
# de +30% avec 60% de volatilité. Le premier indique une tendance linéaire et
# régulière (momentum de haute qualité) ; le second peut être un simple spike
# ponctuel suivi d'un retournement brutal.
#
# Ratio = momentum_12m (%) / volatility_1y (%)  [sans risk-free rate]
# Ce score est orthogonal au momentum absolu : il qualifie la "qualité" du mouvement.
# ---------------------------------------------------------------------------

def compute_momentum_quality_score(momentum_12m: Optional[float], volatility_1y: Optional[float]) -> float:
    """
    Score de qualité du momentum basé sur un ratio Sharpe-like simplifié.

    ratio = momentum_12m / volatility_1y

    Récompense les titres dont le gain est produit de façon régulière (trend following)
    et pénalise les spikes ponctuels même si le retour final est identique.

    Retourne 50 (neutre) si l'une ou l'autre donnée est absente.
    """
    if momentum_12m is None or volatility_1y is None or volatility_1y <= 0:
        return 50.0
    ratio = momentum_12m / volatility_1y
    if ratio >= 2.0:
        return 92.0   # Montée linéaire exceptionnelle (ex: +30% avec vol 15%)
    if ratio >= 1.2:
        return 78.0   # Bonne qualité de momentum
    if ratio >= 0.5:
        return 65.0   # Qualité modérée
    if ratio >= 0.0:
        return 52.0   # Légèrement positif
    if ratio >= -0.5:
        return 38.0   # Légèrement négatif
    if ratio >= -1.2:
        return 25.0   # Baisse régulière
    return 12.0       # Effondrement progressif


def compute_potential_score(card: Dict[str, Any]) -> int:
    """
    Score 0-100, déterministe.

    Composantes (total 100%):
    - Quality (20%): EBIT margin + ROE + FCF margin + Cash Conversion
    - Growth (15%): Revenue CAGR 3y + tendance de croissance (accélération/décélération)
    - Value (30%): FCF yield + P/E + EV/EBITDA + P/B + PEG + Dividend Yield
    - Momentum (15%): Performance 12 mois
    - Technical (10%): RSI + Signal SMA (50/200, golden/death cross)
    - Risk (10%): Beta + Debt
    """
    identity = card.get("identity", {})
    fin = card.get("financials", {})
    val = card.get("valuation", {})
    mkt = card.get("market", {})
    tech = card.get("technicals", {})

    # Détection secteur financier (banques, assurance, gestion d'actifs)
    # Yahoo Finance utilise "Financial Services" ; MSCI/S&P utilisent "Financials"
    sector = identity.get("sector") or ""
    industry = identity.get("industry") or ""

    # Amélioration Coinbase : `is_financial` est désormais industry-aware.
    # Les banques et assureurs ont des marges EBIT/FCF et un EV/EBITDA structurellement
    # non comparables aux entreprises non-financières (les intérêts et primes entrent dans
    # les coûts d'exploitation, pas comme charges financières hors-exploitation).
    # En revanche, les bourses et plateformes d'échange au sein de "Financial Services"
    # (Coinbase, CME, NASDAQ…) génèrent des revenus de commissions comme une tech :
    # leurs marges SONT significatives et doivent être scorées normalement.
    _FINANCIAL_SECTORS = {"Financial Services", "Financials"}
    industry_lower = industry.lower()
    _is_bank_or_insurance = (
        "bank" in industry_lower
        or "insurance" in industry_lower
        or "mortgage" in industry_lower
        or industry_lower in {
            "asset management",
            "financial conglomerates",
            "savings & cooperative banks",
        }
    )
    is_financial = sector in _FINANCIAL_SECTORS and _is_bank_or_insurance

    # === QUALITY (20%) ===
    # EBIT margin (qualité opérationnelle)
    ebit_margin = to_float(fin.get("ebit_margin"))
    # Pour les sociétés financières (banques, fintech), la marge EBIT n'est pas
    # comparable aux entreprises industrielles/tech. Les seuils 5-30% sont calibrés
    # pour des business modèles non-financiers : un fintech bancaire à 6% d'EBIT margin
    # reçoit un score de ~4/100, ce qui est injuste. On neutralise à 50 (non-disponible).
    if is_financial:
        ebit_margin = None
    ebit_score = compute_ebit_score_sector_aware(ebit_margin, sector)

    # Gross margin — calibré selon le secteur
    gross_margin = to_float(fin.get("gross_margin"))
    gross_margin_score = compute_gross_margin_score_sector_aware(gross_margin, sector)

    # ROE (Return on Equity) — calibré selon le secteur (Amélioration 2)
    roe = to_float(fin.get("roe"))
    roe_score = compute_roe_score_sector_aware(roe, sector)

    # FCF margin (qualité du cash généré)
    fcf_margin = to_float(fin.get("fcf_margin"))
    # Pour les sociétés financières, la FCF margin est structurellement différente :
    # les banques financent leurs activités via des dépôts (passif), pas du capex.
    # La FCF margin d'une banque n'est pas comparable à celle d'une tech/industrielle.
    if is_financial:
        fcf_margin = None
    fcf_margin_score = score_linear(fcf_margin, lo=3.0, hi=20.0)

    # Cash Conversion (qualité des bénéfices)
    cash_conv_fcf = to_float(fin.get("fcf_absolute"))
    cash_conv_ni = to_float(fin.get("net_income"))
    cash_conv_score = compute_cash_conversion_score(cash_conv_fcf, cash_conv_ni)

    # Share Dilution 3Y
    share_dilution = to_float(fin.get("share_dilution_3y"))
    dilution_score = compute_share_dilution_score(share_dilution)

    # ROIC (Return on Invested Capital / ROA)
    roic = to_float(fin.get("roic"))
    roic_score = compute_roic_score(roic)

    # Net Profit Margin (marge nette après impôts et intérêts)
    net_margin = to_float(fin.get("net_margin"))
    net_margin_score = compute_net_margin_score(net_margin)

    # Quality composite : pondération dynamique selon les données disponibles
    quality_components = [("ebit", ebit_score, 0.25, ebit_margin)]
    if gross_margin is not None:
        quality_components.append(("gross", gross_margin_score, 0.15, gross_margin))
    quality_components.append(("roe", roe_score, 0.15, roe))
    if fcf_margin is not None:
        quality_components.append(("fcf_m", fcf_margin_score, 0.18, fcf_margin))
    if cash_conv_fcf is not None:
        quality_components.append(("cash_conv", cash_conv_score, 0.15, cash_conv_fcf))
    if share_dilution is not None:
        quality_components.append(("dilution", dilution_score, 0.12, share_dilution))
    if roic is not None:
        quality_components.append(("roic", roic_score, 0.14, roic))
    if net_margin is not None:
        quality_components.append(("net_margin", net_margin_score, 0.12, net_margin))

    # Insider Ownership (alignement d'intérêts)
    insider_own = to_float(fin.get("insider_ownership"))
    insider_score = compute_insider_ownership_score(insider_own)
    if insider_own is not None:
        quality_components.append(("insider", insider_score, 0.10, insider_own))

    # Gross Margin Trend (expansion ou contraction de la marge brute sur 2 ans)
    gm_trend = to_float(fin.get("gross_margin_trend"))
    gm_trend_score = compute_gross_margin_trend_score(gm_trend)
    if gm_trend is not None:
        quality_components.append(("gm_trend", gm_trend_score, 0.12, gm_trend))

    # Accruals Ratio (qualité des bénéfices — anomalie de Sloan)
    # Détecte si les bénéfices sont soutenus par du cash réel ou des ajustements comptables.
    accruals = to_float(fin.get("accruals_ratio"))
    accruals_score = compute_accruals_score(accruals)
    if accruals is not None:
        quality_components.append(("accruals", accruals_score, 0.13, accruals))

    # Institutional Ownership (confiance du "smart money")
    # Un taux élevé = due diligence professionnelle → validation externe forte.
    inst_own = to_float(fin.get("institutional_ownership"))
    inst_score = compute_institutional_ownership_score(inst_own)
    if inst_own is not None:
        quality_components.append(("institutional", inst_score, 0.10, inst_own))

    # Normaliser les poids pour que le total = 1.0
    total_qw = sum(w for _, _, w, _ in quality_components)
    quality = sum(s * w / total_qw for _, s, w, _ in quality_components)

    # === GROWTH (15%) ===
    rev_cagr = to_float(fin.get("revenue_cagr_3y"))

    # Nettoyer les NaN dans les taux YoY (certains providers renvoient NaN pour les périodes incomplètes)
    raw_yoy = fin.get("revenue_yoy_rates")
    if raw_yoy is not None:
        yoy_rates = [r for r in raw_yoy if r is not None and not (isinstance(r, float) and math.isnan(r))]
        if len(yoy_rates) == 0:
            yoy_rates = None
    else:
        yoy_rates = None

    # Si le CAGR est NaN mais qu'on a des taux YoY valides, calculer via moyenne géométrique
    if (rev_cagr is None or (isinstance(rev_cagr, float) and math.isnan(rev_cagr))) and yoy_rates and len(yoy_rates) >= 2:
        try:
            # Moyenne géométrique : plus précise que la moyenne arithmétique sur séries volatiles
            # Ex : +100% puis -50% → arith. = +25% (faux), géom. = -29% (correct)
            product = 1.0
            for r in yoy_rates:
                product *= (1.0 + r / 100.0)
            rev_cagr = (product ** (1.0 / len(yoy_rates)) - 1.0) * 100.0
        except Exception:
            # Fallback arithmétique si la multiplication échoue (ex: taux très extrêmes)
            rev_cagr = sum(yoy_rates) / len(yoy_rates)

    cagr_score = compute_cagr_score_sector_aware(rev_cagr, sector)

    # Tendance de croissance (accélération/décélération)
    trend_score = compute_growth_trend_score(yoy_rates)

    # Stabilité de la croissance revenue
    stability_score = compute_revenue_stability_score(yoy_rates)

    # EPS Growth (croissance des bénéfices par action)
    eps_growth = to_float(fin.get("eps_growth"))
    eps_growth_score = compute_eps_growth_score(eps_growth)

    # Growth composite : CAGR + tendance + stabilité + EPS Growth
    # L'EPS Growth est pondéré uniquement quand disponible (dynamique)
    if yoy_rates is not None and len(yoy_rates) >= 2:
        if eps_growth is not None:
            growth = 0.45 * cagr_score + 0.20 * trend_score + 0.15 * stability_score + 0.20 * eps_growth_score
        else:
            growth = 0.55 * cagr_score + 0.25 * trend_score + 0.20 * stability_score
    else:
        if eps_growth is not None:
            growth = 0.65 * cagr_score + 0.35 * eps_growth_score
        else:
            growth = cagr_score

    # === VALUE (30%) ===
    # FCF yield TTM
    fcf_yield = to_float(val.get("fcf_yield_ttm"))
    fcf_score = compute_fcf_yield_score_sector_aware(fcf_yield, sector)

    # P/E TTM (inverse) - calibré selon le secteur (Amélioration 2)
    pe = to_float(val.get("pe_ttm"))
    pe_score = compute_pe_score_sector_aware(pe, sector)

    # EV/EBITDA (inverse) — calibré selon le secteur
    # Pour les sociétés financières : l'EBITDA n'est pas une métrique standard
    # (les banques incluent les charges d'intérêts comme coût d'exploitation, pas comme
    # charge financière hors-exploitation). On neutralise pour éviter une pénalisation injuste.
    ev_ebitda = to_float(val.get("ev_ebitda_ttm"))
    if is_financial:
        ev_ebitda_score = 50.0  # Non-applicable aux banques → neutre
    else:
        ev_ebitda_score = compute_ev_ebitda_score_sector_aware(ev_ebitda, sector)

    # P/B ratio (inverse) - ajusté par secteur (sector/industry déjà déclarés en début de fonction)
    pb = to_float(val.get("pb_ratio"))
    pb_score = compute_pb_score_sector_aware(pb, sector, industry)

    # PEG ratio — priorité au pegRatio Yahoo Finance (basé sur croissance EPS 5 ans),
    # sinon fallback calculé depuis P/E TTM / CAGR CA
    peg_ratio = to_float(val.get("peg_ratio"))
    if peg_ratio is None and pe is not None and rev_cagr is not None and rev_cagr > 0:
        peg_ratio = pe / rev_cagr
    peg_score = compute_peg_score(peg_ratio)

    # Forward P/E
    forward_pe = to_float(val.get("forward_pe"))
    forward_pe_sc = compute_forward_pe_score(forward_pe, pe)

    # Dividend Yield (avec payout ratio pour soutenabilité)
    div_yield = to_float(mkt.get("dividend_yield"))
    payout_ratio = to_float(fin.get("payout_ratio"))
    div_score = compute_dividend_score(div_yield, payout_ratio)

    # EV/Sales (inverse) — calibré selon le secteur (amélioration Klarna)
    ev_sales = to_float(val.get("ev_sales_ttm"))
    ev_sales_score = compute_ev_sales_score_sector_aware(ev_sales, sector)

    # Value composite : pondération dynamique
    value_components = [
        ("fcf", fcf_score, 0.16),
        ("pe", pe_score, 0.13),
        ("ev_ebitda", ev_ebitda_score, 0.14),
        ("pb", pb_score, 0.09),
        ("peg", peg_score, 0.14),
        ("div", div_score, 0.10),
    ]
    if forward_pe is not None:
        value_components.append(("fwd_pe", forward_pe_sc, 0.13))
    if ev_sales is not None:
        value_components.append(("ev_sales", ev_sales_score, 0.08))

    # Price / Operating Cash Flow (P/OCF)
    # Complémentaire au FCF yield : valorisation sans pénaliser le capex obligatoire.
    p_ocf = to_float(val.get("price_to_ocf"))
    p_ocf_score = compute_price_to_ocf_score(p_ocf)
    if p_ocf is not None and p_ocf > 0:
        value_components.append(("p_ocf", p_ocf_score, 0.10))

    total_vw = sum(w for _, _, w in value_components)
    value = sum(s * w / total_vw for _, s, w in value_components)

    # Volatilité 1Y — extraite ici pour alimenter à la fois le momentum quality score
    # et le composite de risque (évite une extraction dupliquée plus loin).
    vol_1y = to_float(tech.get("volatility_1y"))

    # === MOMENTUM (15%) — Composite absolu × relatif ===
    # Absolu (multi-timeframe) : tendance de prix brute sur 1M/3M/6M/12M.
    # Relatif (vs ETF secteur) : surperformance ou sous-performance vs le secteur.
    # Blend 60/40 : le momentum absolu reste dominant mais le signal relatif
    # qualifie la force du mouvement (un titre qui monte parce que tout son secteur
    # monte est moins intéressant qu'un titre qui monte malgré un secteur flat).

    # — Momentum absolu (multi-timeframe) —
    _mom_pairs = [
        (to_float(mkt.get("momentum_12m")), 0.40),
        (to_float(mkt.get("momentum_6m")),  0.30),
        (to_float(mkt.get("momentum_3m")),  0.20),
        (to_float(mkt.get("momentum_1m")),  0.10),
    ]
    _mom_avail = [(v, w) for v, w in _mom_pairs if v is not None]
    if _mom_avail:
        _total_mw = sum(w for _, w in _mom_avail)
        abs_momentum = sum(_score_single_momentum(v) * w / _total_mw for v, w in _mom_avail)
    else:
        abs_momentum = 50.0

    # — Momentum relatif (vs ETF secteur) —
    _rel_pairs = [
        (to_float(mkt.get("relative_momentum_12m")), 0.50),
        (to_float(mkt.get("relative_momentum_3m")),  0.30),
        (to_float(mkt.get("relative_momentum_1m")),  0.20),
    ]
    _rel_avail = [(v, w) for v, w in _rel_pairs if v is not None]
    if _rel_avail:
        _total_relw = sum(w for _, w in _rel_avail)
        rel_momentum = sum(compute_relative_momentum_score(v) * w / _total_relw for v, w in _rel_avail)
    else:
        rel_momentum = None

    # — Momentum quality (Sharpe-like : perf / volatilité) —
    # Récompense un momentum linéaire et régulier vs un spike ponctuel de même amplitude.
    mom_12m_raw = to_float(mkt.get("momentum_12m"))
    mom_quality_sc = compute_momentum_quality_score(mom_12m_raw, vol_1y)

    if rel_momentum is not None and vol_1y is not None:
        # 3 signaux disponibles : absolu + relatif + qualité
        momentum = 0.50 * abs_momentum + 0.35 * rel_momentum + 0.15 * mom_quality_sc
    elif rel_momentum is not None:
        momentum = 0.60 * abs_momentum + 0.40 * rel_momentum
    elif vol_1y is not None:
        momentum = 0.85 * abs_momentum + 0.15 * mom_quality_sc
    else:
        momentum = abs_momentum

    # === TECHNICAL (10%) ===
    rsi = to_float(tech.get("rsi_14"))
    rsi_score = compute_rsi_score(rsi)

    # Signal SMA (position prix vs SMA50/SMA200) - NOUVEAU
    current_price = to_float(mkt.get("current_price"))
    sma_50 = to_float(tech.get("sma_50"))
    sma_200 = to_float(tech.get("sma_200"))
    sma_score = compute_sma_score(current_price, sma_50, sma_200)

    # Position 52 semaines
    low_52w = to_float(mkt.get("fifty_two_week_low"))
    high_52w = to_float(mkt.get("fifty_two_week_high"))
    pos_52w_score = compute_52w_position_score(current_price, low_52w, high_52w)

    # MACD
    macd_line = to_float(tech.get("macd_line"))
    macd_signal_val = to_float(tech.get("macd_signal"))
    macd_hist = to_float(tech.get("macd_histogram"))
    macd_score = compute_macd_score(macd_line, macd_signal_val, macd_hist, current_price)

    # Technical composite : RSI + SMA + Position 52 semaines + MACD
    has_sma = sma_50 is not None or sma_200 is not None
    has_52w = low_52w is not None and high_52w is not None
    has_macd = macd_line is not None
    if has_sma and has_52w and has_macd:
        technical = 0.25 * rsi_score + 0.30 * sma_score + 0.20 * pos_52w_score + 0.25 * macd_score
    elif has_sma and has_macd:
        technical = 0.30 * rsi_score + 0.35 * sma_score + 0.35 * macd_score
    elif has_sma and has_52w:
        technical = 0.35 * rsi_score + 0.40 * sma_score + 0.25 * pos_52w_score
    elif has_macd:
        technical = 0.45 * rsi_score + 0.55 * macd_score
    elif has_sma:
        technical = 0.50 * rsi_score + 0.50 * sma_score
    elif has_52w:
        technical = 0.60 * rsi_score + 0.40 * pos_52w_score
    else:
        technical = rsi_score

    # === ANALYST CONSENSUS (10%) ===
    analyst_target = to_float(mkt.get("analyst_target_mean"))
    analyst_count_raw = mkt.get("analyst_count")
    analyst_count = int(analyst_count_raw) if analyst_count_raw is not None else None
    analyst_reco = mkt.get("analyst_recommendation")
    analyst = compute_analyst_score(current_price, analyst_target, analyst_count, analyst_reco)

    # === RISK (10%) ===
    # Beta
    beta = to_float(mkt.get("beta"))
    if beta is None:
        beta_score = 50.0
    elif beta <= 0.8:
        beta_score = 80.0  # Défensif = bonus
    elif beta <= 1.2:
        beta_score = 60.0  # Normal
    elif beta <= 1.5:
        beta_score = 40.0  # Volatil
    else:
        beta_score = 20.0  # Très volatil

    # Debt
    net_debt_ebitda = to_float(fin.get("net_debt_to_ebitda"))
    debt_score = compute_debt_score(net_debt_ebitda)

    # Interest Coverage
    interest_cov = to_float(fin.get("interest_coverage"))
    interest_cov_score = compute_interest_coverage_score(interest_cov)

    # Volatility 1Y (extraite avant le calcul du momentum quality score)
    vol_score = compute_volatility_score(vol_1y)

    # Max Drawdown 1Y
    dd_1y = to_float(tech.get("max_drawdown_1y"))
    dd_score = compute_drawdown_score(dd_1y)

    # Current Ratio (liquidité court terme)
    current_ratio = to_float(fin.get("current_ratio"))
    current_ratio_score = compute_current_ratio_score(current_ratio)

    # Risk composite : pondération dynamique
    risk_components = [
        ("beta", beta_score, 0.20, beta),
        ("debt", debt_score, 0.25, net_debt_ebitda),
    ]
    if interest_cov is not None:
        risk_components.append(("interest_cov", interest_cov_score, 0.20, interest_cov))
    if vol_1y is not None:
        risk_components.append(("vol", vol_score, 0.18, vol_1y))
    if dd_1y is not None:
        risk_components.append(("dd", dd_score, 0.17, dd_1y))
    if current_ratio is not None:
        risk_components.append(("current_ratio", current_ratio_score, 0.15, current_ratio))

    # Short Interest (% du float vendu à découvert)
    short_int = to_float(fin.get("short_interest"))
    short_int_score = compute_short_interest_score(short_int)
    if short_int is not None:
        risk_components.append(("short_interest", short_int_score, 0.12, short_int))

    # Altman Z-Score (prédiction de détresse financière — indicateur composite)
    # Synthétise liquidité, rentabilité, levier et efficacité en un seul signal de solidité.
    altman_z = to_float(fin.get("altman_z"))
    altman_z_sc = compute_altman_z_score(altman_z)
    if altman_z is not None:
        risk_components.append(("altman_z", altman_z_sc, 0.18, altman_z))

    total_rw = sum(w for _, _, w, _ in risk_components)
    risk_score = sum(s * w / total_rw for _, s, w, _ in risk_components)

    # === SCORE FINAL ===
    # Quality: 18%, Growth: 13%, Value: 25%, Momentum: 12%, Technical: 10%, Risk: 10%, Analyst: 12%
    has_analyst = analyst_target is not None
    if has_analyst:
        total = (
            0.18 * quality +
            0.13 * growth +
            0.25 * value +
            0.12 * momentum +
            0.10 * technical +
            0.10 * risk_score +
            0.12 * analyst
        )
    else:
        # Fallback sans données analystes : poids originaux
        total = (
            0.20 * quality +
            0.15 * growth +
            0.30 * value +
            0.15 * momentum +
            0.10 * technical +
            0.10 * risk_score
        )

    # === BONUS/MALUS DE CONVERGENCE PROPORTIONNEL (Amélioration 3) ===
    # Bonus/malus graduel selon le nombre ET la force d'alignement des piliers.
    # Formule : MAX_CONV × (nb_alignés / nb_total) × (0.5 + 0.5 × intensité)
    #   - nb_alignés / nb_total : fraction des piliers alignés (0.75 ou 1.0)
    #   - intensité : à quel point les piliers dépassent le seuil (0 → 1)
    # Plage effective : ≈ 0 à 8 points (vs binaire 3/5 auparavant).
    _BULL_THRESH = 65.0
    _BEAR_THRESH = 35.0
    _MAX_CONV = 8.0

    pillars = [quality, growth, value, risk_score]
    bullish_pillars = [p for p in pillars if p >= _BULL_THRESH]
    bearish_pillars = [p for p in pillars if p <= _BEAR_THRESH]

    if len(bullish_pillars) >= 3:
        avg_excess = sum(p - _BULL_THRESH for p in bullish_pillars) / len(bullish_pillars)
        strength  = len(bullish_pillars) / len(pillars)       # 0.75 ou 1.0
        intensity = min(avg_excess / 35.0, 1.0)               # 0 à 1 selon l'excès
        total = total + _MAX_CONV * strength * (0.5 + 0.5 * intensity)
    elif len(bearish_pillars) >= 3:
        avg_excess = sum(_BEAR_THRESH - p for p in bearish_pillars) / len(bearish_pillars)
        strength  = len(bearish_pillars) / len(pillars)
        intensity = min(avg_excess / 35.0, 1.0)
        total = total - _MAX_CONV * strength * (0.5 + 0.5 * intensity)

    return int(round(clamp(total, 0.0, 100.0)))
