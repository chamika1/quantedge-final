"""
Stress testing.

1) Historical replays: apply TODAY'S recommended weights to the actual asset
   returns of three crisis windows (2008 GFC, 2020 COVID crash, 2022 rate-hike
   bear market). Labelled honestly as hypothetical replays — this portfolio
   was not held then; the exercise shows how its current mix behaves when
   assets fall together.

2) Hypothetical scenario (team-designed): "Stagflation shock + gold spike" —
   simultaneous shocks per asset with correlations stressed toward 1, run as
   a Monte Carlo so the answer is a loss distribution, not a single number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOWS = {
    "2008 Global Financial Crisis": ("2007-10-09", "2009-03-09"),
    "2020 COVID-19 Crash": ("2020-02-19", "2020-03-23"),
    "2022 Rate-Hike Bear Market": ("2022-01-03", "2022-10-12"),
}

# Team-designed hypothetical: 6-month stagflation shock (instantaneous shock
# applied to each asset, informed by 1970s-style stagflation behaviour and the
# 2022 episode: equities down hard, bonds fail to protect because inflation is
# the driver, gold spikes, energy mixed on demand destruction).
HYPOTHETICAL_SHOCKS = {
    "SPY": -0.28, "EFA": -0.30, "EEM": -0.35, "AGG": -0.12,
    "GLD": +0.18, "XLE": -0.10, "XLK": -0.34,
}


def historical_replay(asset_returns: pd.DataFrame, weights: pd.Series,
                      portfolio_value: float = 10_000_000) -> pd.DataFrame:
    rows = []
    port = asset_returns[weights.index] @ weights
    for name, (start, end) in WINDOWS.items():
        seg_assets = asset_returns.loc[start:end]
        seg_port = port.loc[start:end]
        cum_assets = (1 + seg_assets).prod() - 1
        cum_port = (1 + seg_port).prod() - 1
        wealth = (1 + seg_port).cumprod()
        mdd = (wealth / wealth.cummax() - 1).min()
        rows.append({
            "scenario": name, "window": f"{start} to {end}",
            "portfolio_return": float(cum_port),
            "portfolio_loss_usd": float(-cum_port * portfolio_value) if cum_port < 0 else 0.0,
            "max_drawdown_in_window": float(mdd),
            **{f"{t}_return": float(cum_assets[t]) for t in weights.index},
        })
    return pd.DataFrame(rows)


def hypothetical_mc(asset_returns: pd.DataFrame, weights: pd.Series,
                    shocks: dict[str, float] = HYPOTHETICAL_SHOCKS,
                    n: int = 100_000, seed: int = 42,
                    portfolio_value: float = 10_000_000) -> dict:
    """
    Monte Carlo around the shock vector: each asset's outcome = shock +
    noise drawn from a multivariate normal with the assets' daily covariance
    scaled to a 6-month horizon and correlations stressed to >= 0.5 for the
    equity block (crisis correlations rise toward 1).
    """
    cols = list(weights.index)
    rng = np.random.default_rng(seed)
    daily = asset_returns[cols]
    cov = daily.cov().values * 126  # ~6 trading months
    corr = daily.corr().values.copy()
    for i in range(len(cols)):
        for j in range(len(cols)):
            if cols[i] in ("SPY", "EFA", "EEM", "XLK") and cols[j] in ("SPY", "EFA", "EEM", "XLK"):
                corr[i, j] = max(corr[i, j], 0.85)
    sd = np.sqrt(np.diag(cov))
    cov_stressed = corr * np.outer(sd, sd)
    mu = np.array([shocks[c] for c in cols])
    sims = rng.multivariate_normal(mu, cov_stressed, size=n)
    port = sims @ weights.values
    det = float(sum(weights[c] * shocks[c] for c in cols))
    return {
        "shocks": shocks,
        "deterministic_portfolio_impact": det,
        "deterministic_loss_usd": -det * portfolio_value if det < 0 else 0.0,
        "mc_mean": float(port.mean()),
        "mc_var95_loss": float(-np.quantile(port, 0.05)),
        "mc_var99_loss": float(-np.quantile(port, 0.01)),
        "mc_worst_1pct_mean_loss": float(-port[port <= np.quantile(port, 0.01)].mean()),
        "prob_loss_gt_10pct": float((port < -0.10).mean()),
    }
