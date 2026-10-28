"""Load the cleaned datasets produced by scripts/download_data.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PORTFOLIO_VALUE = 10_000_000  # USD, per the client brief


def _read(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / name, index_col=0, parse_dates=True)
    return df.sort_index()


def load_all() -> dict:
    prices = _read("prices_adjclose.csv")
    log_ret = _read("returns_log.csv")
    simple_ret = _read("returns_simple.csv")
    rf = _read("risk_free.csv")["DTB3_pct"]
    rf_daily = (rf / 100.0) / 252.0  # annual % yield -> daily simple rate
    return {"prices": prices, "log_returns": log_ret,
            "simple_returns": simple_ret, "rf_annual_pct": rf,
            "rf_daily": rf_daily}
