#!/usr/bin/env python3
"""Validate the swing-trading development environment end to end."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

SAMPLE_DATA = Path(__file__).resolve().parent.parent / "data" / "sample_ohlcv.csv"


def compute_sma(closes: pd.Series, window: int = 20) -> tuple[float, float]:
    sma = closes.rolling(window=window).mean().iloc[-1]
    latest_close = closes.iloc[-1]
    return float(latest_close), float(sma)


def validate_with_sample_data() -> bool:
    if not SAMPLE_DATA.exists():
        print(f"FAIL: Missing sample data at {SAMPLE_DATA}")
        return False

    data = pd.read_csv(SAMPLE_DATA, index_col=0, parse_dates=True)
    if data.empty:
        print("FAIL: Sample OHLCV data is empty")
        return False

    latest_close, sma_20 = compute_sma(data["Close"])
    print(f"OK: Loaded {len(data)} trading days from sample data")
    print(f"Latest close: ${latest_close:.2f}")
    print(f"20-day SMA: ${sma_20:.2f}")
    return True


def try_live_market_data(ticker: str = "AAPL", attempts: int = 2) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            data = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)
            if data.empty:
                continue
            latest_close, sma_20 = compute_sma(data["Close"])
            print(f"OK: Live fetch returned {len(data)} trading days for {ticker}")
            print(f"Live latest close: ${latest_close:.2f}")
            print(f"Live 20-day SMA: ${sma_20:.2f}")
            return True
        except Exception as exc:  # noqa: BLE001 - report provider errors in smoke test
            if attempt == attempts:
                print(f"WARN: Live market data unavailable ({exc}); sample-data validation still passed")
            else:
                time.sleep(2 * attempt)
    return False


def main() -> int:
    if not validate_with_sample_data():
        return 1

    try_live_market_data()
    print("Environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
