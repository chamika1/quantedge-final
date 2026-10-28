"""
Download and clean real market data for Quant Edge 1.0 Final Challenge.

Sources (approved by the competition brief):
  - Yahoo Finance chart API  -> adjusted close prices for the investable universe
  - FRED (fredgraph CSV)     -> 3-month US T-bill yield (DTB3), risk-free proxy

Cleaning discipline (per brief section 9.2):
  - Adjusted close only (dividends/splits already accounted for)
  - Trading calendars aligned by inner join on common dates; dropped dates counted
  - Log returns for statistical work, simple returns saved alongside
  - Suspected data errors are FLAGGED, not deleted (stale/flat prices, extreme jumps)
  - Augmented Dickey-Fuller stationarity check on every return series

Outputs (data/):
  prices_adjclose.csv, returns_log.csv, returns_simple.csv, risk_free.csv,
  data_quality_report.json
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from statsmodels.tsa.stattools import adfuller

TICKERS = ["SPY", "EFA", "EEM", "AGG", "GLD", "XLE", "XLK"]
START = "2007-01-01"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126 Safari/537.36"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def yahoo_adjclose(ticker: str) -> pd.Series:
    p1 = int(pd.Timestamp(START, tz="UTC").timestamp())
    p2 = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div,split")
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(
        "America/New_York").normalize().tz_localize(None)
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    s = pd.Series(adj, index=ts, name=ticker, dtype=float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def main() -> None:
    raw, report = {}, {"tickers": {}}
    for t in TICKERS:
        s = yahoo_adjclose(t)
        raw[t] = s
        report["tickers"][t] = {
            "rows_raw": int(s.notna().sum()),
            "first": str(s.first_valid_index().date()),
            "last": str(s.last_valid_index().date()),
        }
        print(f"{t}: {s.notna().sum()} rows {s.first_valid_index().date()} -> "
              f"{s.last_valid_index().date()}")

    prices = pd.DataFrame(raw)
    n_before = len(prices)
    prices = prices.dropna(how="any")  # calendar alignment: common trading days only
    report["calendar"] = {
        "rows_union_calendar": int(n_before),
        "rows_aligned": int(len(prices)),
        "rows_dropped_by_alignment": int(n_before - len(prices)),
        "start": str(prices.index.min().date()),
        "end": str(prices.index.max().date()),
    }

    # --- flags, never deletions -------------------------------------------------
    log_ret = np.log(prices / prices.shift(1)).dropna()
    simple_ret = prices.pct_change().dropna()
    flags = {}
    for t in TICKERS:
        stale = int((prices[t].diff() == 0).sum())
        jumps = log_ret[t][log_ret[t].abs() > 0.35]
        flags[t] = {
            "zero_change_days_flagged": stale,
            "extreme_jump_days_flagged": int(len(jumps)),
            "extreme_jump_dates": [str(d.date()) for d in jumps.index],
        }
    report["flags"] = flags

    # --- stationarity (ADF on log returns) --------------------------------------
    adf = {}
    for t in TICKERS:
        stat, pval, *_ = adfuller(log_ret[t].dropna(), autolag="AIC")
        adf[t] = {"adf_stat": round(float(stat), 3), "p_value": float(pval),
                  "stationary_at_5pct": bool(pval < 0.05)}
    report["adf_log_returns"] = adf

    # --- risk-free rate: FRED DTB3 ----------------------------------------------
    fred = pd.read_csv(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd=2007-01-01",
        parse_dates=["observation_date"], index_col="observation_date")
    fred.columns = ["DTB3_pct"]
    fred = fred.reindex(prices.index).ffill().bfill()

    prices.to_csv(DATA_DIR / "prices_adjclose.csv")
    log_ret.to_csv(DATA_DIR / "returns_log.csv")
    simple_ret.to_csv(DATA_DIR / "returns_simple.csv")
    fred.to_csv(DATA_DIR / "risk_free.csv")
    (DATA_DIR / "data_quality_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["calendar"], indent=2))
    print("ADF p-values:", {k: v["p_value"] for k, v in adf.items()})


if __name__ == "__main__":
    main()
