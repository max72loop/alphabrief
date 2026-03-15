# mytrader_generator/utils/ticker_utils.py
"""Utilities for handling international ticker symbols."""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Mapping of exchange codes to yfinance suffixes
EXCHANGE_SUFFIXES = {
    # Asia-Pacific
    "HKG": ".HK",      # Hong Kong
    "HKEX": ".HK",
    "HK": ".HK",
    "TYO": ".T",       # Tokyo
    "TSE": ".T",
    "JPX": ".T",
    "KRX": ".KS",      # Korea (KOSPI)
    "KSC": ".KS",
    "KOSDAQ": ".KQ",   # Korea (KOSDAQ)
    "SHA": ".SS",      # Shanghai
    "SHE": ".SZ",      # Shenzhen
    "SZ": ".SZ",
    "ASX": ".AX",      # Australia
    "SGX": ".SI",      # Singapore
    "NSE": ".NS",      # India (NSE)
    "BSE": ".BO",      # India (Bombay)
    "TWO": ".TW",      # Taiwan
    "TPE": ".TW",

    # Europe
    "EPA": ".PA",      # Paris (Euronext)
    "PAR": ".PA",
    "EURONEXT": ".PA",
    "ETR": ".DE",      # Germany (Xetra)
    "FRA": ".DE",
    "XETRA": ".DE",
    "GER": ".DE",
    "LON": ".L",       # London
    "LSE": ".L",
    "AMS": ".AS",      # Amsterdam
    "BRU": ".BR",      # Brussels
    "LIS": ".LS",      # Lisbon
    "SWX": ".SW",      # Swiss
    "EBS": ".SW",
    "VIE": ".VI",      # Vienna
    "MIL": ".MI",      # Milan
    "BIT": ".MI",
    "BME": ".MC",      # Madrid
    "MCE": ".MC",
    "OSL": ".OL",      # Oslo
    "CPH": ".CO",      # Copenhagen
    "STO": ".ST",      # Stockholm
    "HEL": ".HE",      # Helsinki

    # Americas (non-US)
    "TSX": ".TO",      # Toronto
    "CVE": ".V",       # TSX Venture
    "BMV": ".MX",      # Mexico
    "BOVESPA": ".SA",  # Brazil
    "SAO": ".SA",

    # Middle East
    "TLV": ".TA",      # Tel Aviv

    # US exchanges (no suffix needed)
    "NYSE": "",
    "NASDAQ": "",
    "AMEX": "",
    "ARCA": "",
    "BATS": "",
    "NMS": "",
    "NYQ": "",
    "NGM": "",
    "NCM": "",
    "NAS": "",
}

# Common exchange name variations
EXCHANGE_ALIASES = {
    "HONG KONG": "HKG",
    "PARIS": "EPA",
    "EURONEXT PARIS": "EPA",
    "TOKYO": "TYO",
    "FRANKFURT": "ETR",
    "XETRA": "ETR",
    "LONDON": "LON",
    "MILAN": "MIL",
    "MADRID": "BME",
    "AMSTERDAM": "AMS",
    "ZURICH": "SWX",
    "SWISS": "SWX",
    "TORONTO": "TSX",
    "SYDNEY": "ASX",
    "SHANGHAI": "SHA",
    "SHENZHEN": "SHE",
    "SEOUL": "KRX",
    "KOREA": "KRX",
    "MUMBAI": "NSE",
    "INDIA": "NSE",
    "SAO PAULO": "SAO",
    "BRAZIL": "SAO",
    "SINGAPORE": "SGX",
    "TAIWAN": "TWO",
}


def normalize_ticker(raw_input: str) -> str:
    """
    Normalize a ticker symbol to yfinance format.

    Accepts various formats:
    - "AAPL" -> "AAPL" (US stock)
    - "9961.HK" -> "9961.HK" (already correct)
    - "HKG:9961" -> "9961.HK"
    - "HKG: 9961" -> "9961.HK"
    - "MC.PA" -> "MC.PA" (already correct)
    - "EPA:MC" -> "MC.PA"
    - "005930.KS" -> "005930.KS" (Korean stocks keep leading zeros)

    Args:
        raw_input: Raw ticker input from user

    Returns:
        Normalized ticker symbol for yfinance
    """
    raw_input = raw_input.strip().upper()

    if not raw_input:
        return raw_input

    # Check if it's already in yfinance format (has a dot suffix)
    if "." in raw_input and ":" not in raw_input:
        return raw_input

    # Handle "EXCHANGE:SYMBOL" format (e.g., "HKG:9961", "EPA:MC")
    if ":" in raw_input:
        parts = raw_input.split(":", 1)
        if len(parts) == 2:
            exchange = parts[0].strip()
            symbol = parts[1].strip()

            # Check if exchange is known
            suffix = EXCHANGE_SUFFIXES.get(exchange)
            if suffix is not None:
                # Handle Hong Kong tickers - remove leading zeros except for Korean stocks
                if suffix == ".HK" and symbol.isdigit():
                    symbol = symbol.lstrip("0") or "0"
                return f"{symbol}{suffix}"

            # Check aliases
            exchange_code = EXCHANGE_ALIASES.get(exchange)
            if exchange_code:
                suffix = EXCHANGE_SUFFIXES.get(exchange_code, "")
                if suffix == ".HK" and symbol.isdigit():
                    symbol = symbol.lstrip("0") or "0"
                return f"{symbol}{suffix}"

    # If no special format detected, return as-is (assume US stock)
    return raw_input


def parse_ticker_input(raw_input: str) -> Tuple[str, Optional[str]]:
    """
    Parse ticker input and return (normalized_ticker, exchange_hint).

    Args:
        raw_input: Raw user input

    Returns:
        Tuple of (normalized ticker, optional exchange hint for display)
    """
    normalized = normalize_ticker(raw_input)

    # Extract exchange hint from suffix
    exchange_hint = None
    if "." in normalized:
        suffix = "." + normalized.split(".")[-1]
        for exchange, ex_suffix in EXCHANGE_SUFFIXES.items():
            if ex_suffix == suffix:
                exchange_hint = exchange
                break

    return normalized, exchange_hint


def get_common_exchanges() -> list:
    """Return list of common exchange formats for help text."""
    return [
        ("USA (NYSE/NASDAQ)", "AAPL, MSFT, GOOGL"),
        ("Hong Kong", "9961.HK ou HKG:9961"),
        ("Paris/Euronext", "MC.PA ou EPA:MC"),
        ("Frankfurt/Xetra", "SAP.DE ou ETR:SAP"),
        ("London", "SHEL.L ou LON:SHEL"),
        ("Tokyo", "7203.T ou TYO:7203"),
        ("Toronto", "RY.TO ou TSX:RY"),
        ("Zurich", "NESN.SW ou SWX:NESN"),
        ("Milan", "ENI.MI ou MIL:ENI"),
        ("Amsterdam", "ASML.AS ou AMS:ASML"),
        ("Korea", "005930.KS ou KRX:005930"),
        ("Australia", "BHP.AX ou ASX:BHP"),
    ]


def validate_ticker(ticker: str) -> Tuple[bool, str]:
    """
    Validate a ticker by checking if yfinance can find it.

    Args:
        ticker: Normalized ticker symbol

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}

        name = info.get("shortName") or info.get("longName")
        if name:
            exchange = info.get("exchange", "Unknown")
            return True, f"{name} ({exchange})"
        else:
            return False, "Ticker non trouve"
    except Exception as e:
        return False, f"Erreur: {str(e)}"
