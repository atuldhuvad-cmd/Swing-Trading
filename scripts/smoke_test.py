#!/usr/bin/env python3
"""Validate the swing-trading development environment end to end."""

from __future__ import annotations

import sys
import time

import pandas as pd
import yfinance as yf


def fetch_market_data(ticker: str, attempts: int = 4) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            data = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)
            if not data.empty:
                return data
        except Exception as exc:  # noqa: BLE001 - surface provider errors in smoke test
            last_error = exc
        if attempt < attempts:
            time.sleep(2 * attempt)
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def main() -> int:
    ticker = "AAPL"
    data = fetch_market_data(ticker)

    if data.empty:
        print(f"FAIL: No market data returned for {ticker}")
        return 1

    closes = data["Close"]
    sma_20 = closes.rolling(window=20).mean().iloc[-1]
    latest_close = closes.iloc[-1]

    if pd.isna(sma_20):
        print(f"FAIL: Could not compute 20-day SMA for {ticker}")
        return 1

    print(f"OK: Fetched {len(data)} trading days for {ticker}")
    print(f"Latest close: ${latest_close:.2f}")
    print(f"20-day SMA: ${sma_20:.2f}")
    print("Environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
