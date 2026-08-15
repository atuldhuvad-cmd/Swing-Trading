# Swing-Trading

Python development environment for swing-trading research and strategy development.

## Setup

Dependencies are installed automatically by the Cloud Agent environment. To set up locally:

```bash
./.cursor/install.sh
source .venv/bin/activate
```

## Validate the environment

```bash
source .venv/bin/activate
python scripts/smoke_test.py
```

The smoke test fetches recent market data for AAPL, computes a 20-day simple moving average, and confirms the core analysis stack is working.

## Stack

- Python 3.12
- pandas, numpy, matplotlib
- yfinance for market data
