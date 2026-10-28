"""
VaR backtesting: Kupiec POF, Christoffersen independence & conditional
coverage, and the Basel traffic-light classification.

A VaR *exception* on day t means the realised loss exceeded the VaR forecast
made for that day (forecast uses only data available before day t).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .risk import var_historical, var_parametric


# --------------------------------------------------------------------------- #
# Rolling one-step-ahead VaR forecasts + exceptions
# --------------------------------------------------------------------------- #
def rolling_backtest(returns: pd.Series, level: float = 0.99, window: int = 250,
                     method: str = "historical") -> pd.DataFrame:
    """Forecast VaR_t from returns[t-window : t]; exception if loss_t > VaR_t."""
    fn = var_historical if method == "historical" else var_parametric
    idx, forecasts = [], []
    r = returns.reset_index(drop=True)
    for t in range(window, len(r)):
        idx.append(returns.index[t])
        forecasts.append(fn(r.iloc[t - window:t], level))
    out = pd.DataFrame({"return": returns.loc[idx].values,
                        "VaR": forecasts}, index=idx)
    out["exception"] = (-out["return"] > out["VaR"]).astype(int)
    return out


# --------------------------------------------------------------------------- #
# Kupiec (1995) Proportion-Of-Failures test
# --------------------------------------------------------------------------- #
def kupiec_pof(exceptions: int, n: int, level: float) -> dict:
    p = 1 - level  # expected exception probability
    x = exceptions
    if x == 0:
        lr = -2 * n * np.log(1 - p)
    else:
        # log-space: direct powers underflow for large n
        log_null = (n - x) * np.log(1 - p) + x * np.log(p)
        log_alt = (n - x) * np.log(1 - x / n) + x * np.log(x / n)
        lr = -2 * (log_null - log_alt)
    return {"LR": float(lr), "p_value": float(1 - stats.chi2.cdf(lr, 1)),
            "exceptions": x, "n": n, "expected": n * p,
            "reject_at_5pct": bool(lr > 3.841)}


# --------------------------------------------------------------------------- #
# Christoffersen (1998) independence + conditional coverage
# --------------------------------------------------------------------------- #
def _transitions(exc: np.ndarray) -> tuple[int, int, int, int]:
    a = exc[:-1]; b = exc[1:]
    return (int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum()),
            int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum()))


def christoffersen(exceptions_series: pd.Series, level: float) -> dict:
    exc = exceptions_series.to_numpy().astype(int)
    n00, n01, n10, n11 = _transitions(exc)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    pi01 = n01 / max(n00 + n01, 1)
    pi11 = n11 / max(n10 + n11, 1)

    def loglik(p01, p11):
        ll = 0.0
        if n00: ll += n00 * np.log(max(1 - p01, 1e-12))
        if n01: ll += n01 * np.log(max(p01, 1e-12))
        if n10: ll += n10 * np.log(max(1 - p11, 1e-12))
        if n11: ll += n11 * np.log(max(p11, 1e-12))
        return ll

    lr_ind = -2 * (loglik(pi, pi) - loglik(pi01, pi11))
    kup = kupiec_pof(int(exc.sum()), len(exc), level)
    lr_cc = kup["LR"] + lr_ind
    return {
        "LR_independence": float(lr_ind),
        "p_independence": float(1 - stats.chi2.cdf(lr_ind, 1)),
        "LR_conditional_coverage": float(lr_cc),
        "p_conditional_coverage": float(1 - stats.chi2.cdf(lr_cc, 2)),
        "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11},
    }


# --------------------------------------------------------------------------- #
# Basel traffic light (250 observations, 99% VaR)
# --------------------------------------------------------------------------- #
def basel_traffic_light(exceptions: int, n: int = 250, level: float = 0.99) -> dict:
    """Basel zones from the binomial CDF of the exception count."""
    cdf = stats.binom.cdf(exceptions, n, 1 - level)
    if cdf < 0.95:
        zone = "GREEN"
    elif cdf < 0.9999:
        zone = "YELLOW"
    else:
        zone = "RED"
    return {"zone": zone, "binomial_cdf": float(cdf), "exceptions": exceptions, "n": n}


def backtest_summary(returns: pd.Series, level: float = 0.99, window: int = 250,
                     method: str = "historical") -> dict:
    """Full backtest bundle for one method/level."""
    bt = rolling_backtest(returns, level, window, method)
    exc = int(bt["exception"].sum()); n = len(bt)
    out = {"method": method, "level": level, "window": window, "n_obs": n,
           "exceptions": exc, "exception_rate": exc / n,
           "kupiec": kupiec_pof(exc, n, level),
           "christoffersen": christoffersen(bt["exception"], level),
           "basel_last_250": basel_traffic_light(int(bt["exception"].tail(250).sum()),
                                                 min(250, n), level),
           "series": bt}
    return out
