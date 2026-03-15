"""
btc_buy_signal_analyzer.py - Analyseur de Signaux d'Achat Bitcoin v2
=====================================================================

Ce module calcule un score composite pour déterminer s'il est intéressant
d'acheter du Bitcoin en utilisant plusieurs algorithmes et indicateurs :

1.  Pi Cycle Top Indicator - Détection des tops de marché
2.  MVRV Z-Score - Valorisation relative
3.  Stock-to-Flow Model - Rareté et valorisation à long terme
4.  Fear & Greed Index - Sentiment de marché
5.  RSI Multi-Timeframe - Momentum technique
6.  Puell Multiple - Profitabilité des mineurs
7.  Rainbow Price Bands - Position dans le cycle
8.  200 Week Moving Average Heatmap - Cycle à long terme
9.  Golden Ratio Multiplier - Niveaux de support/résistance
10. MACD Multi-Timeframe - Momentum et tendance
11. Halving Cycle Position - Position dans le cycle de halving (4 ans)
12. Volatilité (ATR) - Niveau de volatilité et risque

Améliorations v2:
- Scoring continu par interpolation (plus de sauts discrets)
- Score de confiance basé sur l'accord entre indicateurs
- 3 nouveaux indicateurs (MACD, Halving Cycle, Volatilité)

Score final: 0-100 avec recommandation claire (ACHAT FORT / ACHAT / NEUTRE / PRUDENCE / ÉVITER)
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import math
import pandas as pd
import numpy as np

# =============== Interpolation continue ===============

def interpolate_score(value: float, breakpoints: List[Tuple[float, float]]) -> float:
    """
    Interpole un score de manière continue entre des points de contrôle.

    breakpoints: liste de (valeur_seuil, score) triée par valeur croissante.
    Retourne un score interpolé linéairement entre les breakpoints.
    """
    if not breakpoints:
        return 50.0

    # En dessous du premier breakpoint
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]

    # Au-dessus du dernier breakpoint
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]

    # Interpolation linéaire entre deux breakpoints adjacents
    for i in range(len(breakpoints) - 1):
        v0, s0 = breakpoints[i]
        v1, s1 = breakpoints[i + 1]
        if v0 <= value <= v1:
            if v1 == v0:
                return s0
            t = (value - v0) / (v1 - v0)
            return s0 + t * (s1 - s0)

    return breakpoints[-1][1]


# =============== Configuration ===============

@dataclass
class BTCBuySignalConfig:
    """Configuration des poids et seuils pour le scoring"""
    # Poids de chaque indicateur (total redistribué sur 12 indicateurs)
    weight_pi_cycle: float = 10.0
    weight_mvrv: float = 13.0
    weight_stock_to_flow: float = 8.0
    weight_fear_greed: float = 10.0
    weight_rsi_multi: float = 12.0
    weight_puell: float = 7.0
    weight_rainbow: float = 8.0
    weight_200wma: float = 8.0
    weight_golden_ratio: float = 6.0
    weight_macd: float = 8.0
    weight_halving_cycle: float = 5.0
    weight_volatility: float = 5.0

    # Seuils pour les recommandations
    threshold_strong_buy: float = 75.0
    threshold_buy: float = 60.0
    threshold_neutral: float = 45.0
    threshold_caution: float = 30.0
    # En dessous de caution = ÉVITER


@dataclass
class BTCBuySignalInputs:
    """
    Données d'entrée pour l'analyse des signaux d'achat
    """
    # Prix et données de base
    price: float
    price_history: Optional[pd.Series] = None  # Historique des prix (au moins 2 ans)

    # Moyennes mobiles (calculées si non fournies)
    ma_111: Optional[float] = None  # 111 DMA
    ma_350: Optional[float] = None  # 350 DMA
    ma_200: Optional[float] = None  # 200 DMA
    ma_200_weekly: Optional[float] = None  # 200 WMA

    # On-chain
    mvrv_z: Optional[float] = None
    realized_price: Optional[float] = None
    puell_multiple: Optional[float] = None

    # Stock-to-Flow
    s2f_ratio: Optional[float] = None
    s2f_model_price: Optional[float] = None
    days_since_halving: Optional[int] = None

    # Sentiment
    fear_greed_index: Optional[int] = None

    # Technique
    rsi_daily: Optional[float] = None
    rsi_weekly: Optional[float] = None
    rsi_monthly: Optional[float] = None

    # MACD (nouveaux)
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_weekly_histogram: Optional[float] = None

    # Volatilité (nouveau)
    atr_14: Optional[float] = None         # ATR 14 jours
    atr_14_pct: Optional[float] = None     # ATR en % du prix

    # Timestamp
    date: Optional[datetime] = None


# =============== Indicateurs individuels ===============

def calculate_pi_cycle_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Pi Cycle Top Indicator

    Signale les tops quand 111DMA croise au-dessus de 350DMA x 2
    Score élevé = loin d'un top = bon pour acheter

    Returns:
        (score 0-100, signal, details)
    """
    details = {}

    if inputs.price_history is None or len(inputs.price_history) < 350:
        # Pas assez de données, utiliser les MAs fournies si disponibles
        if inputs.ma_111 is None or inputs.ma_350 is None:
            return 50.0, "NEUTRE", {"message": "Données insuffisantes"}

        ma_111 = inputs.ma_111
        ma_350_x2 = inputs.ma_350 * 2
    else:
        # Calculer les MAs
        ma_111 = float(inputs.price_history.rolling(111).mean().iloc[-1])
        ma_350_x2 = float(inputs.price_history.rolling(350).mean().iloc[-1]) * 2

    # Calculer la distance entre les deux MAs
    distance_pct = ((ma_350_x2 - ma_111) / ma_350_x2) * 100

    details['ma_111'] = ma_111
    details['ma_350_x2'] = ma_350_x2
    details['distance_pct'] = distance_pct

    # Scoring continu par interpolation
    breakpoints = [(-10, 5), (0, 20), (5, 40), (15, 65), (30, 82), (50, 95)]
    score = interpolate_score(distance_pct, breakpoints)

    if distance_pct > 30:
        signal = "LOIN DU TOP"
    elif distance_pct > 15:
        signal = "ZONE FAVORABLE"
    elif distance_pct > 5:
        signal = "VIGILANCE"
    elif distance_pct > 0:
        signal = "PROCHE DU TOP"
    else:
        signal = "SIGNAL DE TOP!"

    return score, signal, details


def calculate_mvrv_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    MVRV Z-Score

    Mesure la valorisation relative par rapport à la valeur réalisée

    Zones:
    - Z < 0 : Sous-évalué (vert) = ACHAT FORT
    - 0 < Z < 2 : Valorisation raisonnable = ACHAT
    - 2 < Z < 5 : Surévalué = PRUDENCE
    - Z > 5 : Extrêmement surévalué = ÉVITER
    """
    details = {}

    if inputs.mvrv_z is None:
        # Estimer à partir du prix et prix réalisé si disponible
        if inputs.realized_price is not None and inputs.price > 0:
            # Estimation simplifiée du Z-Score
            ratio = inputs.price / inputs.realized_price
            # Normalisation approximative
            z_estimate = (ratio - 1) * 2
            details['estimated'] = True
            mvrv_z = z_estimate
        else:
            return 50.0, "NEUTRE", {"message": "MVRV Z-Score non disponible"}
    else:
        mvrv_z = inputs.mvrv_z
        details['estimated'] = False

    details['mvrv_z'] = mvrv_z

    # Scoring continu
    breakpoints = [(-1.0, 100), (-0.5, 95), (0, 85), (1, 75), (2, 55), (3.5, 35), (5, 18), (7, 5)]
    score = interpolate_score(mvrv_z, breakpoints)

    if mvrv_z < -0.5:
        signal = "SURVENTE EXTRÊME"
    elif mvrv_z < 0:
        signal = "SOUS-ÉVALUÉ"
    elif mvrv_z < 1:
        signal = "BON PRIX"
    elif mvrv_z < 2:
        signal = "VALORISATION CORRECTE"
    elif mvrv_z < 3.5:
        signal = "SURÉVALUÉ"
    elif mvrv_z < 5:
        signal = "TRÈS SURÉVALUÉ"
    else:
        signal = "EUPHORIE EXTRÊME"

    return score, signal, details


def calculate_stock_to_flow_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Stock-to-Flow Model

    Compare le prix actuel au prix prédit par le modèle S2F

    Formule: Prix S2F = e^(a + b * ln(S2F_ratio))
    Coefficients historiques: a ≈ -1.84, b ≈ 3.36
    """
    details = {}

    # Calculer le S2F ratio si non fourni
    if inputs.s2f_ratio is None:
        # Estimation basée sur le cycle de halving
        # Supply total ≈ 19.6M BTC (2024)
        # Flow annuel ≈ 328,500 BTC (6.25 BTC/bloc * 6 blocs/h * 24h * 365j)
        # Après halving 2024: 3.125 BTC/bloc

        if inputs.days_since_halving is not None:
            # Ajuster selon la position dans le cycle
            if inputs.days_since_halving < 0:
                # Avant halving
                annual_flow = 6.25 * 6 * 24 * 365  # ~328,500
            else:
                # Après halving 2024
                annual_flow = 3.125 * 6 * 24 * 365  # ~164,250
        else:
            # Valeur par défaut post-halving 2024
            annual_flow = 164250

        current_supply = 19600000  # Approximation
        s2f_ratio = current_supply / annual_flow
    else:
        s2f_ratio = inputs.s2f_ratio

    details['s2f_ratio'] = s2f_ratio

    # Calculer le prix prédit par S2F
    # Coefficients du modèle Plan B (ajustés)
    a = -1.84
    b = 3.36
    s2f_model_price = math.exp(a + b * math.log(s2f_ratio))

    if inputs.s2f_model_price is not None:
        s2f_model_price = inputs.s2f_model_price

    details['s2f_model_price'] = s2f_model_price

    # Ratio prix actuel / prix modèle
    if s2f_model_price > 0:
        price_ratio = inputs.price / s2f_model_price
    else:
        price_ratio = 1.0

    details['price_ratio'] = price_ratio

    # Scoring continu
    breakpoints = [(0.1, 100), (0.3, 90), (0.5, 78), (0.8, 65), (1.2, 50), (2.0, 30), (3.0, 15)]
    score = interpolate_score(price_ratio, breakpoints)

    if price_ratio < 0.3:
        signal = "TRÈS SOUS-ÉVALUÉ vs S2F"
    elif price_ratio < 0.5:
        signal = "SOUS-ÉVALUÉ vs S2F"
    elif price_ratio < 0.8:
        signal = "LÉGÈREMENT SOUS S2F"
    elif price_ratio < 1.2:
        signal = "PROCHE DU MODÈLE S2F"
    elif price_ratio < 2.0:
        signal = "AU-DESSUS DU S2F"
    else:
        signal = "TRÈS SURÉVALUÉ vs S2F"

    return score, signal, details


def calculate_fear_greed_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Fear & Greed Index - Contrarian indicator
    """
    details = {}

    if inputs.fear_greed_index is None:
        return 50.0, "NEUTRE", {"message": "Fear & Greed Index non disponible"}

    fg = inputs.fear_greed_index
    details['fear_greed'] = fg

    # Scoring continu inversé (peur = opportunité)
    breakpoints = [(0, 100), (10, 95), (24, 85), (35, 70), (44, 58), (55, 48), (65, 35), (74, 22), (85, 12), (100, 3)]
    score = interpolate_score(fg, breakpoints)

    if fg <= 10:
        signal = "PEUR EXTRÊME - OPPORTUNITÉ"
    elif fg <= 24:
        signal = "PEUR ÉLEVÉE"
    elif fg <= 35:
        signal = "PEUR MODÉRÉE"
    elif fg <= 44:
        signal = "LÉGÈRE PEUR"
    elif fg <= 55:
        signal = "NEUTRE"
    elif fg <= 65:
        signal = "LÉGÈRE CUPIDITÉ"
    elif fg <= 74:
        signal = "CUPIDITÉ"
    elif fg <= 85:
        signal = "CUPIDITÉ ÉLEVÉE"
    else:
        signal = "EUPHORIE EXTRÊME"

    return score, signal, details


def calculate_rsi_multi_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    RSI Multi-Timeframe

    Combine RSI Daily, Weekly et Monthly pour une vue complète
    RSI < 30 = Survente
    RSI 30-70 = Normal
    RSI > 70 = Surachat
    """
    details = {}
    scores = []

    def rsi_to_buy_score(rsi: float) -> float:
        """Convertit RSI en score d'achat (inversé) avec interpolation continue"""
        bp = [(10, 100), (20, 92), (30, 80), (40, 65), (50, 55), (60, 42), (70, 30), (80, 18), (90, 8)]
        return interpolate_score(rsi, bp)

    # RSI Daily (poids: 30%)
    if inputs.rsi_daily is not None:
        daily_score = rsi_to_buy_score(inputs.rsi_daily)
        scores.append(('daily', daily_score, 0.30))
        details['rsi_daily'] = inputs.rsi_daily
        details['daily_score'] = daily_score

    # RSI Weekly (poids: 40%)
    if inputs.rsi_weekly is not None:
        weekly_score = rsi_to_buy_score(inputs.rsi_weekly)
        scores.append(('weekly', weekly_score, 0.40))
        details['rsi_weekly'] = inputs.rsi_weekly
        details['weekly_score'] = weekly_score

    # RSI Monthly (poids: 30%)
    if inputs.rsi_monthly is not None:
        monthly_score = rsi_to_buy_score(inputs.rsi_monthly)
        scores.append(('monthly', monthly_score, 0.30))
        details['rsi_monthly'] = inputs.rsi_monthly
        details['monthly_score'] = monthly_score

    if not scores:
        return 50.0, "NEUTRE", {"message": "RSI non disponible"}

    # Calculer le score pondéré
    total_weight = sum(s[2] for s in scores)
    weighted_score = sum(s[1] * s[2] for s in scores) / total_weight

    details['weighted_score'] = weighted_score

    # Déterminer le signal
    if weighted_score >= 80:
        signal = "SURVENTE MULTI-TF"
    elif weighted_score >= 65:
        signal = "ZONE D'ACHAT"
    elif weighted_score >= 50:
        signal = "NEUTRE"
    elif weighted_score >= 35:
        signal = "SURACHAT LÉGER"
    else:
        signal = "SURACHAT"

    return weighted_score, signal, details


def calculate_puell_multiple_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Puell Multiple

    Ratio entre l'émission journalière (en USD) et sa moyenne 365j

    < 0.5 = Zone d'achat
    0.5-1.0 = Accumuler
    1.0-2.0 = Neutre
    > 2.0 = Prudence
    > 4.0 = Vendre
    """
    details = {}

    if inputs.puell_multiple is None:
        return 50.0, "NEUTRE", {"message": "Puell Multiple non disponible"}

    puell = inputs.puell_multiple
    details['puell_multiple'] = puell

    breakpoints = [(0.1, 100), (0.3, 95), (0.5, 85), (0.8, 68), (1.2, 50), (2.0, 30), (4.0, 12), (6.0, 3)]
    score = interpolate_score(puell, breakpoints)

    if puell < 0.3:
        signal = "CAPITULATION - ACHAT FORT"
    elif puell < 0.5:
        signal = "ZONE D'ACHAT OPTIMALE"
    elif puell < 0.8:
        signal = "ZONE D'ACCUMULATION"
    elif puell < 1.2:
        signal = "NEUTRE"
    elif puell < 2.0:
        signal = "AU-DESSUS MOYENNE"
    elif puell < 4.0:
        signal = "ZONE DE PRUDENCE"
    else:
        signal = "ZONE DE VENTE"

    return score, signal, details


def calculate_rainbow_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Rainbow Price Bands

    Basé sur une régression logarithmique du prix Bitcoin
    Les bandes colorées indiquent la position dans le cycle
    """
    details = {}

    if inputs.price_history is None or len(inputs.price_history) < 365:
        return 50.0, "NEUTRE", {"message": "Historique insuffisant pour Rainbow"}

    # Calculer les bandes Rainbow (simplifiées)
    # Formule de base: log_price = a * log(days) + b

    # Nombre de jours depuis le genesis block (approximatif)
    days_since_genesis = len(inputs.price_history)

    # Coefficients approximatifs du Rainbow
    a = 5.8  # Pente
    b = -17.0  # Intercept

    # Prix médian du modèle
    log_median_price = a * math.log(days_since_genesis) + b
    median_price = math.exp(log_median_price)

    # Bandes (facteurs multiplicatifs)
    bands = {
        'fire_sale': 0.15,      # Bleu foncé - Fire Sale
        'buy': 0.35,            # Bleu - Accumuler
        'accumulate': 0.55,     # Vert - Toujours pas cher
        'hold': 0.85,           # Jaune-vert - HODL
        'consider_sell': 1.15,  # Jaune - Penser à vendre
        'bubble': 1.50,         # Orange - Bulle en formation
        'max_bubble': 2.20,     # Rouge - Bulle maximale
    }

    price_ratio = inputs.price / median_price if median_price > 0 else 1.0

    details['median_price'] = median_price
    details['price_ratio'] = price_ratio

    # Scoring continu
    breakpoints = [
        (bands['fire_sale'] * 0.5, 100), (bands['fire_sale'], 95),
        (bands['buy'], 85), (bands['accumulate'], 70),
        (bands['hold'], 50), (bands['consider_sell'], 35),
        (bands['bubble'], 20), (bands['max_bubble'], 8)
    ]
    score = interpolate_score(price_ratio, breakpoints)

    if price_ratio < bands['fire_sale']:
        signal, details['band'] = "FIRE SALE", 'fire_sale'
    elif price_ratio < bands['buy']:
        signal, details['band'] = "BUY ZONE", 'buy'
    elif price_ratio < bands['accumulate']:
        signal, details['band'] = "ACCUMULATE", 'accumulate'
    elif price_ratio < bands['hold']:
        signal, details['band'] = "HODL ZONE", 'hold'
    elif price_ratio < bands['consider_sell']:
        signal, details['band'] = "CONSIDER SELLING", 'consider_sell'
    elif price_ratio < bands['bubble']:
        signal, details['band'] = "BUBBLE FORMING", 'bubble'
    else:
        signal, details['band'] = "MAXIMUM BUBBLE", 'max_bubble'

    return score, signal, details


def calculate_200wma_heatmap_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    200 Week Moving Average Heatmap

    Le prix par rapport à la 200WMA (1400 jours) donne une indication
    du cycle de marché à long terme
    """
    details = {}

    if inputs.ma_200_weekly is not None:
        ma_200w = inputs.ma_200_weekly
    elif inputs.price_history is not None and len(inputs.price_history) >= 1400:
        ma_200w = float(inputs.price_history.rolling(1400).mean().iloc[-1])
    else:
        return 50.0, "NEUTRE", {"message": "200WMA non disponible"}

    ratio = inputs.price / ma_200w if ma_200w > 0 else 1.0

    details['ma_200w'] = ma_200w
    details['price_ratio'] = ratio

    # Croissance mensuelle de la 200WMA
    if inputs.price_history is not None and len(inputs.price_history) >= 1430:
        ma_200w_month_ago = float(inputs.price_history.rolling(1400).mean().iloc[-30])
        monthly_growth = ((ma_200w - ma_200w_month_ago) / ma_200w_month_ago) * 100
    else:
        monthly_growth = 0

    details['monthly_growth'] = monthly_growth

    # Scoring continu
    breakpoints = [(0.3, 100), (0.5, 95), (0.8, 85), (1.0, 70), (1.5, 50), (2.5, 30), (4.0, 15), (6.0, 5)]
    score = interpolate_score(ratio, breakpoints)

    if ratio < 0.5:
        signal = "TRÈS EN DESSOUS 200WMA"
    elif ratio < 0.8:
        signal = "SOUS 200WMA - OPPORTUNITÉ"
    elif ratio < 1.0:
        signal = "LÉGÈREMENT SOUS 200WMA"
    elif ratio < 1.5:
        signal = "AU-DESSUS 200WMA"
    elif ratio < 2.5:
        signal = "BIEN AU-DESSUS"
    elif ratio < 4.0:
        signal = "ZONE CHAUDE"
    else:
        signal = "ZONE DE SURCHAUFFE"

    return score, signal, details


def calculate_golden_ratio_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Golden Ratio Multiplier

    Utilise la 350DMA multipliée par 1.6 (approx. ratio d'or)
    et d'autres niveaux Fibonacci pour identifier les cycles
    """
    details = {}

    if inputs.price_history is None or len(inputs.price_history) < 350:
        if inputs.ma_350 is not None:
            ma_350 = inputs.ma_350
        else:
            return 50.0, "NEUTRE", {"message": "350DMA non disponible"}
    else:
        ma_350 = float(inputs.price_history.rolling(350).mean().iloc[-1])

    # Niveaux Golden Ratio
    levels = {
        'support_strong': ma_350 * 0.618,  # Support fort
        'support': ma_350 * 1.0,           # Support
        'neutral': ma_350 * 1.618,         # Niveau neutre (golden ratio)
        'resistance': ma_350 * 2.0,        # Résistance
        'top_zone': ma_350 * 2.618,        # Zone de top (Fib extension)
    }

    details['ma_350'] = ma_350
    details['levels'] = levels

    price = inputs.price

    # Scoring continu
    breakpoints = [
        (levels['support_strong'] * 0.5, 100), (levels['support_strong'], 92),
        (levels['support'], 78), (levels['neutral'], 58),
        (levels['resistance'], 38), (levels['top_zone'], 18),
        (levels['top_zone'] * 1.5, 5)
    ]
    score = interpolate_score(price, breakpoints)

    if price < levels['support_strong']:
        signal = "SOUS SUPPORT FORT"
    elif price < levels['support']:
        signal = "PRÈS DU SUPPORT"
    elif price < levels['neutral']:
        signal = "ZONE NEUTRE"
    elif price < levels['resistance']:
        signal = "APPROCHE RÉSISTANCE"
    elif price < levels['top_zone']:
        signal = "AU-DESSUS RÉSISTANCE"
    else:
        signal = "ZONE DE TOP"

    return score, signal, details


# =============== Nouveaux Indicateurs v2 ===============

def calculate_macd_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    MACD Multi-Timeframe

    Analyse la convergence/divergence des moyennes mobiles pour détecter
    le momentum et les changements de tendance.
    - Histogramme positif et croissant = momentum haussier
    - Croisement MACD/Signal = signal de changement
    """
    details = {}

    if inputs.price_history is None or len(inputs.price_history) < 35:
        if inputs.macd_histogram is not None:
            histogram = inputs.macd_histogram
            details['macd_histogram'] = histogram
            details['source'] = 'provided'
        else:
            return 50.0, "NEUTRE", {"message": "Données insuffisantes pour MACD"}
    else:
        prices = inputs.price_history
        # MACD daily: EMA(12) - EMA(26), signal = EMA(9) du MACD
        ema_12 = prices.ewm(span=12, adjust=False).mean()
        ema_26 = prices.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        details['macd_line'] = float(macd_line.iloc[-1])
        details['signal_line'] = float(signal_line.iloc[-1])
        details['histogram'] = float(histogram.iloc[-1])
        details['source'] = 'calculated'

        # Normaliser l'histogramme en % du prix pour comparabilité
        histogram_pct = (histogram / prices) * 100

        # Tendance de l'histogramme (croissant ou décroissant)
        hist_trend = float(histogram.iloc[-1]) - float(histogram.iloc[-5]) if len(histogram) >= 5 else 0
        details['hist_trend'] = hist_trend

    # Score basé sur l'histogramme normalisé
    if 'histogram' in details:
        hist_val = details['histogram']
        price = float(inputs.price)
        hist_pct = (hist_val / price) * 100 if price > 0 else 0
        details['histogram_pct'] = hist_pct

        # Histogramme positif = momentum haussier = bon pour acheter si pas en surachat
        # On veut : histogramme très négatif = survente = score élevé (contrarien)
        #           histogramme légèrement positif et croissant = bon momentum
        #           histogramme très positif = surachat = score bas

        # Score hybride: contrarien pour les extrêmes, momentum pour le milieu
        breakpoints = [(-3.0, 92), (-1.5, 80), (-0.5, 65), (0.0, 55), (0.5, 60), (1.0, 55), (2.0, 35), (3.5, 15)]
        base_score = interpolate_score(hist_pct, breakpoints)

        # Bonus si histogramme croissant (momentum qui s'améliore)
        if 'hist_trend' in details:
            trend_pct = (details['hist_trend'] / price) * 100 if price > 0 else 0
            if trend_pct > 0.1:
                base_score = min(100, base_score + 8)
            elif trend_pct < -0.1:
                base_score = max(0, base_score - 8)

        score = base_score
    else:
        histogram = details.get('macd_histogram', 0)
        score = 50.0

    # MACD weekly bonus si disponible
    if inputs.macd_weekly_histogram is not None:
        details['weekly_histogram'] = inputs.macd_weekly_histogram
        if inputs.macd_weekly_histogram > 0:
            score = min(100, score + 5)
        elif inputs.macd_weekly_histogram < 0:
            score = max(0, score - 5)

    if score >= 75:
        signal = "MOMENTUM ACHAT FORT"
    elif score >= 60:
        signal = "MOMENTUM FAVORABLE"
    elif score >= 45:
        signal = "MOMENTUM NEUTRE"
    elif score >= 30:
        signal = "MOMENTUM BAISSIER"
    else:
        signal = "SURACHAT - PRUDENCE"

    return score, signal, details


def calculate_halving_cycle_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Halving Cycle Position

    Le cycle Bitcoin de ~4 ans suit historiquement un pattern:
    - Mois 0-6 après halving: Accumulation (très favorable)
    - Mois 6-12: Début du bull run (favorable)
    - Mois 12-18: Bull run actif (modéré, attention au timing)
    - Mois 18-24: Zone de top potentiel (prudence)
    - Mois 24-36: Bear market / correction (contrarien = opportunité)
    - Mois 36-48: Fin de bear / pré-halving (accumulation)
    """
    details = {}

    if inputs.days_since_halving is None:
        return 50.0, "NEUTRE", {"message": "Date de halving non disponible"}

    days = inputs.days_since_halving
    months = days / 30.44  # Conversion en mois approximatifs
    cycle_pct = (days % 1461) / 1461 * 100  # Position dans le cycle de 4 ans (%)

    details['days_since_halving'] = days
    details['months_since_halving'] = round(months, 1)
    details['cycle_position_pct'] = round(cycle_pct, 1)

    # Scoring basé sur la position dans le cycle (mois)
    # Points de contrôle: (mois, score)
    breakpoints = [
        (0, 85), (3, 88), (6, 82), (9, 72), (12, 62),
        (15, 50), (18, 38), (21, 28), (24, 35),
        (30, 55), (36, 70), (42, 78), (48, 85)
    ]
    score = interpolate_score(months % 48, breakpoints)

    if months < 6:
        signal = "POST-HALVING - ACCUMULATION"
    elif months < 12:
        signal = "DÉBUT BULL RUN"
    elif months < 18:
        signal = "BULL RUN ACTIF"
    elif months < 24:
        signal = "ZONE DE TOP POTENTIEL"
    elif months < 36:
        signal = "CORRECTION / BEAR"
    else:
        signal = "PRÉ-HALVING - ACCUMULATION"

    return score, signal, details


def calculate_volatility_score(inputs: BTCBuySignalInputs) -> Tuple[float, str, Dict]:
    """
    Analyse de Volatilité (ATR)

    L'Average True Range (ATR) mesure la volatilité.
    - Volatilité basse = consolidation = souvent précède un mouvement (favorable)
    - Volatilité modérée = marché sain
    - Volatilité extrême = risque élevé (défavorable pour l'entrée)
    """
    details = {}

    if inputs.atr_14_pct is not None:
        atr_pct = inputs.atr_14_pct
        details['atr_pct'] = atr_pct
        details['source'] = 'provided'
    elif inputs.price_history is not None and len(inputs.price_history) >= 15:
        prices = inputs.price_history
        # Calcul ATR simplifié (pas de High/Low, on utilise les variations daily)
        daily_range = prices.diff().abs()
        atr_14 = float(daily_range.rolling(14).mean().iloc[-1])
        atr_pct = (atr_14 / float(prices.iloc[-1])) * 100

        details['atr_14'] = atr_14
        details['atr_pct'] = round(atr_pct, 2)
        details['source'] = 'calculated'

        # Volatilité relative: ATR actuel vs ATR moyen sur 90j
        if len(prices) >= 104:
            atr_90 = float(daily_range.rolling(14).mean().rolling(90).mean().iloc[-1])
            vol_ratio = atr_14 / atr_90 if atr_90 > 0 else 1.0
            details['vol_ratio'] = round(vol_ratio, 2)
    else:
        return 50.0, "NEUTRE", {"message": "Données insuffisantes pour la volatilité"}

    # Score: volatilité basse = bon (consolidation), extrême = mauvais (risque)
    # ATR% typique BTC: 1-2% = bas, 3-4% = modéré, 5%+ = élevé, 8%+ = extrême
    breakpoints = [(0.5, 60), (1.5, 72), (2.5, 65), (3.5, 55), (5.0, 40), (7.0, 25), (10.0, 12)]
    score = interpolate_score(atr_pct, breakpoints)

    # Bonus si la volatilité est en contraction (souvent précède un breakout)
    if 'vol_ratio' in details:
        vol_ratio = details['vol_ratio']
        if vol_ratio < 0.7:
            score = min(100, score + 10)
            details['vol_compression'] = True
        elif vol_ratio > 1.5:
            score = max(0, score - 8)
            details['vol_compression'] = False

    if atr_pct < 1.5:
        signal = "VOLATILITÉ BASSE - CONSOLIDATION"
    elif atr_pct < 3.5:
        signal = "VOLATILITÉ MODÉRÉE"
    elif atr_pct < 5.0:
        signal = "VOLATILITÉ ÉLEVÉE"
    else:
        signal = "VOLATILITÉ EXTRÊME - RISQUE"

    return score, signal, details


# =============== Score Composite ===============

def calculate_confidence(scores: List[float]) -> Tuple[float, str]:
    """
    Calcule un score de confiance basé sur l'accord entre indicateurs.

    Si tous les indicateurs pointent dans la même direction, la confiance est haute.
    Si les indicateurs sont contradictoires, la confiance est basse.

    Returns:
        (confidence 0-100, description)
    """
    if len(scores) < 3:
        return 50.0, "Pas assez d'indicateurs"

    mean = np.mean(scores)
    std = np.std(scores)

    # Coefficient de variation inversé : plus std est petit, plus les indicateurs concordent
    # CV typique: 0 = parfait accord, 30+ = désaccord total
    cv = (std / mean * 100) if mean > 0 else 100

    # Compter les indicateurs qui concordent (même côté de 50)
    bullish = sum(1 for s in scores if s >= 55)
    bearish = sum(1 for s in scores if s < 45)
    total = len(scores)
    agreement_ratio = max(bullish, bearish) / total

    # Score de confiance combiné
    cv_score = max(0, 100 - cv * 2)  # 0-100, inversé
    agreement_score = agreement_ratio * 100

    confidence = cv_score * 0.4 + agreement_score * 0.6

    if confidence >= 80:
        desc = "Très haute - indicateurs fortement alignés"
    elif confidence >= 60:
        desc = "Haute - majorité des indicateurs concordent"
    elif confidence >= 40:
        desc = "Modérée - signaux mixtes"
    elif confidence >= 25:
        desc = "Faible - indicateurs contradictoires"
    else:
        desc = "Très faible - forte divergence"

    return round(confidence, 1), desc


def calculate_buy_signal_score(inputs: BTCBuySignalInputs,
                               config: Optional[BTCBuySignalConfig] = None) -> Dict:
    """
    Calcule le score composite d'achat Bitcoin v2

    Args:
        inputs: BTCBuySignalInputs avec toutes les données disponibles
        config: Configuration des poids (optionnel)

    Returns:
        Dict avec score, recommandation, confiance et détails
    """
    if config is None:
        config = BTCBuySignalConfig()

    results = {}
    weighted_scores = []

    indicators = [
        ('pi_cycle', calculate_pi_cycle_score, config.weight_pi_cycle),
        ('mvrv', calculate_mvrv_score, config.weight_mvrv),
        ('stock_to_flow', calculate_stock_to_flow_score, config.weight_stock_to_flow),
        ('fear_greed', calculate_fear_greed_score, config.weight_fear_greed),
        ('rsi_multi', calculate_rsi_multi_score, config.weight_rsi_multi),
        ('puell', calculate_puell_multiple_score, config.weight_puell),
        ('rainbow', calculate_rainbow_score, config.weight_rainbow),
        ('200wma', calculate_200wma_heatmap_score, config.weight_200wma),
        ('golden_ratio', calculate_golden_ratio_score, config.weight_golden_ratio),
        ('macd', calculate_macd_score, config.weight_macd),
        ('halving_cycle', calculate_halving_cycle_score, config.weight_halving_cycle),
        ('volatility', calculate_volatility_score, config.weight_volatility),
    ]

    for name, func, weight in indicators:
        score, signal, details = func(inputs)
        results[name] = {'score': round(score, 1), 'signal': signal, 'details': details}
        if 'message' not in details:
            weighted_scores.append((score, weight))

    # Calculer le score final pondéré
    if weighted_scores:
        total_weight = sum(w for _, w in weighted_scores)
        final_score = sum(s * w for s, w in weighted_scores) / total_weight
    else:
        final_score = 50.0

    # Calculer la confiance
    active_scores = [s for s, _ in weighted_scores]
    confidence, confidence_desc = calculate_confidence(active_scores)

    # Déterminer la recommandation
    if final_score >= config.threshold_strong_buy:
        recommendation = "ACHAT FORT"
        recommendation_color = "#00FF88"
        recommendation_icon = "🟢"
        recommendation_message = "Conditions exceptionnelles pour accumuler du Bitcoin. La majorité des indicateurs sont favorables."
    elif final_score >= config.threshold_buy:
        recommendation = "ACHAT"
        recommendation_color = "#00FFF0"
        recommendation_icon = "▲"
        recommendation_message = "Bon moment pour investir dans le Bitcoin via DCA ou achat spot."
    elif final_score >= config.threshold_neutral:
        recommendation = "NEUTRE"
        recommendation_color = "#FFD700"
        recommendation_icon = "–"
        recommendation_message = "Conditions mixtes. DCA modéré recommandé, évitez les positions importantes."
    elif final_score >= config.threshold_caution:
        recommendation = "PRUDENCE"
        recommendation_color = "#FF8C00"
        recommendation_icon = "⚠️"
        recommendation_message = "Conditions défavorables. Réduisez les achats et sécurisez les profits si possible."
    else:
        recommendation = "ÉVITER"
        recommendation_color = "#FF0080"
        recommendation_icon = "▼"
        recommendation_message = "Conditions très défavorables. Évitez d'acheter, risque élevé de correction."

    # Ajouter un avertissement si confiance faible
    if confidence < 35:
        recommendation_message += " (Attention: signaux contradictoires, confiance faible)"

    return {
        'score': round(final_score, 1),
        'recommendation': recommendation,
        'recommendation_color': recommendation_color,
        'recommendation_icon': recommendation_icon,
        'recommendation_message': recommendation_message,
        'confidence': confidence,
        'confidence_desc': confidence_desc,
        'indicators': results,
        'indicators_available': len(weighted_scores),
        'indicators_total': 12,
        'config': config
    }


# =============== Utilitaires pour récupérer les données ===============

def fetch_fear_greed_index() -> Optional[int]:
    """
    Récupère l'index Fear & Greed depuis l'API Alternative.me
    """
    try:
        import urllib.request
        import json

        url = "https://api.alternative.me/fng/?limit=1"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data and 'data' in data and len(data['data']) > 0:
                return int(data['data'][0]['value'])
    except Exception as e:
        print(f"Erreur récupération Fear & Greed: {e}")

    return None


def fetch_btc_price_history(days: int = 730) -> Optional[pd.Series]:
    """
    Récupère l'historique des prix Bitcoin via yfinance
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker("BTC-USD")
        df = ticker.history(period=f"{days}d", interval="1d")

        if not df.empty and 'Close' in df.columns:
            return df['Close']
    except Exception as e:
        print(f"Erreur récupération historique BTC: {e}")

    return None


def create_inputs_from_live_data() -> BTCBuySignalInputs:
    """
    Crée les inputs à partir de données live (yfinance + APIs)
    """
    # Récupérer l'historique des prix
    price_history = fetch_btc_price_history(days=1500)

    if price_history is None or price_history.empty:
        raise ValueError("Impossible de récupérer l'historique des prix")

    current_price = float(price_history.iloc[-1])

    # Calculer les MAs
    ma_111 = float(price_history.rolling(111).mean().iloc[-1]) if len(price_history) >= 111 else None
    ma_200 = float(price_history.rolling(200).mean().iloc[-1]) if len(price_history) >= 200 else None
    ma_350 = float(price_history.rolling(350).mean().iloc[-1]) if len(price_history) >= 350 else None
    ma_200_weekly = float(price_history.rolling(1400).mean().iloc[-1]) if len(price_history) >= 1400 else None

    # Calculer RSI
    def calculate_rsi(series: pd.Series, period: int = 14) -> float:
        delta = series.diff()
        up = delta.where(delta > 0, 0.0)
        down = -delta.where(delta < 0, 0.0)
        rs = up.rolling(period).mean() / (down.rolling(period).mean() + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    rsi_daily = calculate_rsi(price_history, 14) if len(price_history) >= 14 else None

    # RSI Weekly (approximé avec données daily)
    if len(price_history) >= 98:  # 14 semaines * 7 jours
        weekly_prices = price_history.resample('W').last().dropna()
        if len(weekly_prices) >= 14:
            rsi_weekly = calculate_rsi(weekly_prices, 14)
        else:
            rsi_weekly = None
    else:
        rsi_weekly = None

    # Fear & Greed Index
    fear_greed = fetch_fear_greed_index()

    # Days since halving (approximatif - halving Avril 2024)
    halving_date = datetime(2024, 4, 20)
    days_since_halving = (datetime.now() - halving_date).days

    # MACD (calculé à partir de l'historique)
    macd_line_val = None
    macd_signal_val = None
    macd_histogram_val = None
    macd_weekly_hist = None

    if len(price_history) >= 35:
        ema_12 = price_history.ewm(span=12, adjust=False).mean()
        ema_26 = price_history.ewm(span=26, adjust=False).mean()
        macd_line_series = ema_12 - ema_26
        signal_line_series = macd_line_series.ewm(span=9, adjust=False).mean()
        macd_line_val = float(macd_line_series.iloc[-1])
        macd_signal_val = float(signal_line_series.iloc[-1])
        macd_histogram_val = macd_line_val - macd_signal_val

        # MACD weekly
        if len(price_history) >= 200:
            weekly_prices = price_history.resample('W').last().dropna()
            if len(weekly_prices) >= 35:
                w_ema12 = weekly_prices.ewm(span=12, adjust=False).mean()
                w_ema26 = weekly_prices.ewm(span=26, adjust=False).mean()
                w_macd = w_ema12 - w_ema26
                w_signal = w_macd.ewm(span=9, adjust=False).mean()
                macd_weekly_hist = float((w_macd - w_signal).iloc[-1])

    # ATR (volatilité)
    atr_14_val = None
    atr_14_pct_val = None
    if len(price_history) >= 15:
        daily_range = price_history.diff().abs()
        atr_14_val = float(daily_range.rolling(14).mean().iloc[-1])
        atr_14_pct_val = (atr_14_val / current_price) * 100

    return BTCBuySignalInputs(
        price=current_price,
        price_history=price_history,
        ma_111=ma_111,
        ma_200=ma_200,
        ma_350=ma_350,
        ma_200_weekly=ma_200_weekly,
        rsi_daily=rsi_daily,
        rsi_weekly=rsi_weekly,
        fear_greed_index=fear_greed,
        days_since_halving=days_since_halving,
        macd_line=macd_line_val,
        macd_signal=macd_signal_val,
        macd_histogram=macd_histogram_val,
        macd_weekly_histogram=macd_weekly_hist,
        atr_14=atr_14_val,
        atr_14_pct=atr_14_pct_val,
        date=datetime.now()
    )


def get_buy_signal_analysis() -> Dict:
    """
    Point d'entrée principal - récupère les données et calcule le score
    """
    try:
        inputs = create_inputs_from_live_data()
        return calculate_buy_signal_score(inputs)
    except Exception as e:
        return {
            'score': None,
            'recommendation': "ERREUR",
            'recommendation_color': "#FF0000",
            'recommendation_icon': "❌",
            'recommendation_message': f"Erreur lors de l'analyse: {str(e)}",
            'indicators': {},
            'error': str(e)
        }


# =============== Tests ===============

if __name__ == "__main__":
    print("=== Test Bitcoin Buy Signal Analyzer ===\n")

    result = get_buy_signal_analysis()

    if result['score'] is not None:
        print(f"Score Global: {result['score']}/100")
        print(f"Recommandation: {result['recommendation_icon']} {result['recommendation']}")
        print(f"Confiance: {result['confidence']}% - {result['confidence_desc']}")
        print(f"Message: {result['recommendation_message']}")
        print(f"\nIndicateurs disponibles: {result['indicators_available']}/{result['indicators_total']}")
        print("\nDétails par indicateur:")
        for name, data in result['indicators'].items():
            print(f"  - {name}: {data['score']:.1f} ({data['signal']})")
    else:
        print(f"Erreur: {result['recommendation_message']}")
