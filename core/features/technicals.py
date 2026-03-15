from __future__ import annotations

import pandas as pd
import yfinance as yf
from typing import Dict, Optional

def compute_technicals(ticker: str) -> Dict[str, Optional[float]]:
    """
    Computes RSI (14), SMA (50), SMA (200), MACD, volatility and max drawdown.
    Returns a dictionary with these values (last available).
    """
    output = {
        "rsi_14": None,
        "sma_50": None,
        "sma_200": None,
        "macd_line": None,
        "macd_signal": None,
        "macd_histogram": None,
        "volatility_1y": None,
        "max_drawdown_1y": None,
    }
    
    try:
        # Fetch enough history for 200 SMA + some buffer. 1y is ~252 trading days.
        # We need at least 200 points.
        hist = yf.Ticker(ticker).history(period="2y")
        
        if hist is None or hist.empty:
            return output
            
        close = hist["Close"]
        
        if len(close) < 200:
            # Maybe we can still compute RSI if > 14
            pass

        # SMA 50
        if len(close) >= 50:
            sma_50 = close.rolling(window=50).mean()
            output["sma_50"] = float(sma_50.iloc[-1])

        # SMA 200
        if len(close) >= 200:
            sma_200 = close.rolling(window=200).mean()
            output["sma_200"] = float(sma_200.iloc[-1])

        # MACD (12, 26, 9) — lissé sur 3 jours pour réduire la volatilité
        if len(close) >= 35:  # Need at least 26 + 9 points
            ema_12 = close.ewm(span=12, adjust=False).mean()
            ema_26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            macd_signal = macd_line.ewm(span=9, adjust=False).mean()
            macd_histogram = macd_line - macd_signal
            output["macd_line"] = float(macd_line.iloc[-3:].mean())
            output["macd_signal"] = float(macd_signal.iloc[-3:].mean())
            output["macd_histogram"] = float(macd_histogram.iloc[-3:].mean())

        # Volatility 1Y (annualized std of daily returns)
        if len(close) >= 252:
            close_1y = close.iloc[-252:]
        else:
            close_1y = close
        if len(close_1y) >= 20:
            daily_returns = close_1y.pct_change().dropna()
            if len(daily_returns) >= 20:
                output["volatility_1y"] = float(daily_returns.std() * (252 ** 0.5) * 100)  # en %

        # Max Drawdown 1Y
        if len(close_1y) >= 20:
            cummax = close_1y.cummax()
            drawdown = (close_1y - cummax) / cummax
            output["max_drawdown_1y"] = float(drawdown.min() * 100)  # en % (négatif)

        # RSI 14 — lissé sur 3 jours pour réduire la volatilité
        if len(close) >= 15:
            delta = close.diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)

            # Use exponential moving average (Wilder's smoothing)
            # alpha = 1/14
            ma_up = up.ewm(alpha=1/14, adjust=False).mean()
            ma_down = down.ewm(alpha=1/14, adjust=False).mean()

            rs = ma_up / ma_down
            rsi = 100 - (100 / (1 + rs))
            output["rsi_14"] = float(rsi.iloc[-3:].mean())
            
    except Exception:
        pass

    return output
