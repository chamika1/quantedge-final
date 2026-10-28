"""
Portfolio construction and performance analytics.

Candidate portfolios (all long-only, fully invested):
  - Equal Weight (naive benchmark)
  - Global Minimum Variance
  - Maximum Sharpe (tangency)
  - Risk Parity (equal risk contribution)
  - RECOMMENDED: Constrained Minimum Variance under the client's
    Investment Policy constraints (5% floor per asset so no asset class is
    abandoned on one window's estimates, single-name cap 40%, AGG floor 25%,
    total equity cap 60%, GLD cap 20%) — loss avoidance first.

Expected returns / covariance are estimated on a trailing estimation window;
Ledoit-Wolf shrinkage is used for the covariance to stabilise the optimiser.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

TRADING_DAYS = 252
EQUITY = ["SPY", "EFA", "EEM", "XLE", "XLK"]


# --------------------------------------------------------------------------- #
# Estimation helpers
# --------------------------------------------------------------------------- #
def annualised_stats(returns: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    mu = returns.mean() * TRADING_DAYS
    lw = LedoitWolf().fit(returns.values)
    cov = pd.DataFrame(lw.covariance_ * TRADING_DAYS,
                       index=returns.columns, columns=returns.columns)
    return mu, cov


def _solve(obj, w0, bounds, extra_cons=()):
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}, *extra_cons]
    res = minimize(obj, w0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-10})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def _bounds(cols, cap=1.0, floor=0.0):
    return [(floor, cap)] * len(cols)


def min_variance(mu, cov, cols, extra_cons=(), cap=1.0, floor=0.0) -> pd.Series:
    w = _solve(lambda w: w @ cov.values @ w, np.ones(len(cols)) / len(cols),
               _bounds(cols, cap, floor), extra_cons)
    return pd.Series(w, index=cols)


def max_sharpe(mu, cov, cols, rf_annual: float) -> pd.Series:
    def neg_sharpe(w):
        ex = w @ mu.values - rf_annual
        vol = np.sqrt(w @ cov.values @ w)
        return -ex / vol if vol > 0 else 0.0
    w = _solve(neg_sharpe, np.ones(len(cols)) / len(cols), _bounds(cols))
    return pd.Series(w, index=cols)


def risk_parity(cov, cols) -> pd.Series:
    def obj(w):
        port_var = w @ cov.values @ w
        mrc = cov.values @ w
        rc = w * mrc / port_var
        return np.sum((rc - 1 / len(cols)) ** 2)
    w = _solve(obj, np.ones(len(cols)) / len(cols), _bounds(cols))
    return pd.Series(w, index=cols)


def recommended_weights(mu, cov, cols) -> pd.Series:
    """Constrained minimum variance under the client's policy limits."""
    idx = {c: i for i, c in enumerate(cols)}
    extra = [
        {"type": "ineq", "fun": lambda w: w[idx["AGG"]] - 0.25},                    # AGG floor
        {"type": "ineq", "fun": lambda w: 0.60 - sum(w[idx[e]] for e in EQUITY if e in idx)},  # equity cap
        {"type": "ineq", "fun": lambda w: 0.20 - w[idx["GLD"]]},                    # GLD cap
    ]
    return min_variance(mu, cov, cols, extra_cons=extra, cap=0.40, floor=0.05)


def candidate_portfolios(returns_window: pd.DataFrame, rf_annual: float) -> dict[str, pd.Series]:
    mu, cov = annualised_stats(returns_window)
    cols = list(returns_window.columns)
    return {
        "Equal Weight": pd.Series(1 / len(cols), index=cols),
        "Minimum Variance": min_variance(mu, cov, cols),
        "Maximum Sharpe": max_sharpe(mu, cov, cols, rf_annual),
        "Risk Parity": risk_parity(cov, cols),
        "Recommended (Constrained Min-Var)": recommended_weights(mu, cov, cols),
    }


# --------------------------------------------------------------------------- #
# Portfolio series + KPIs
# --------------------------------------------------------------------------- #
def portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    return returns[weights.index] @ weights


def drawdown_series(returns: pd.Series) -> pd.Series:
    wealth = (1 + returns).cumprod()
    return wealth / wealth.cummax() - 1


def kpis(returns: pd.Series, rf_daily: pd.Series, benchmark: pd.Series) -> dict:
    """Full KPI set from the brief (Layer 1), computed on simple returns."""
    r = returns.dropna()
    rf = rf_daily.reindex(r.index).fillna(0.0)
    excess = r - rf
    n_years = len(r) / TRADING_DAYS
    total = (1 + r).prod()
    cagr = total ** (1 / n_years) - 1
    ann_ret = r.mean() * TRADING_DAYS
    ann_vol = r.std(ddof=1) * np.sqrt(TRADING_DAYS)
    sharpe = excess.mean() / excess.std(ddof=1) * np.sqrt(TRADING_DAYS)
    downside = excess[excess < 0]
    sortino = (excess.mean() * TRADING_DAYS) / (downside.std(ddof=1) * np.sqrt(TRADING_DAYS))
    dd = drawdown_series(r)
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan

    # CAPM vs benchmark (SPY): beta, Jensen's alpha, Treynor
    bench = benchmark.reindex(r.index).dropna()
    rr, bb = r.loc[bench.index], bench
    rrf = rf.reindex(rr.index).fillna(0.0)
    cov = np.cov(rr - rrf, bb - rrf, ddof=1)
    beta = cov[0, 1] / cov[1, 1]
    alpha_daily = (rr - rrf).mean() - beta * (bb - rrf).mean()
    jensen_alpha = alpha_daily * TRADING_DAYS
    treynor = (ann_ret - rf.mean() * TRADING_DAYS) / beta if beta != 0 else np.nan
    active = rr - bb
    info_ratio = active.mean() / active.std(ddof=1) * np.sqrt(TRADING_DAYS)
    return {
        "CAGR": float(cagr), "AnnReturn": float(ann_ret), "AnnVol": float(ann_vol),
        "Sharpe": float(sharpe), "Sortino": float(sortino),
        "MaxDrawdown": float(max_dd), "Calmar": float(calmar),
        "Beta_vs_SPY": float(beta), "JensenAlpha": float(jensen_alpha),
        "Treynor": float(treynor), "InformationRatio": float(info_ratio),
        "WorstDay": float(r.min()), "BestDay": float(r.max()),
        "Skew": float(r.skew()), "Kurtosis": float(r.kurtosis()),
    }


def risk_contributions(weights: pd.Series, cov_annual: pd.DataFrame) -> pd.DataFrame:
    w = weights.values
    cov = cov_annual.loc[weights.index, weights.index].values
    port_vol = np.sqrt(w @ cov @ w)
    mrc = cov @ w / port_vol
    crc = w * mrc
    return pd.DataFrame({"weight": weights, "marginal_risk": mrc,
                         "component_risk": crc,
                         "pct_risk": crc / port_vol * 100})
