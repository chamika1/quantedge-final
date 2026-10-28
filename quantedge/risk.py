"""
Risk measurement engine: VaR (3 methods), Expected Shortfall, EVT (POT/GPD).

Conventions
-----------
- Input returns are daily *simple* portfolio returns (fractions, e.g. -0.02 = -2%).
- Losses are positive numbers: L = -r.
- VaR and ES are reported as positive fractions of portfolio value
  (multiply by portfolio value for currency amounts).
- Confidence levels follow the brief: 0.95 and 0.99 (plus 0.975 / 0.995 where useful).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


# --------------------------------------------------------------------------- #
# Historical (non-parametric)
# --------------------------------------------------------------------------- #
def var_historical(returns: pd.Series, level: float) -> float:
    """Empirical quantile of the loss distribution."""
    return float(np.quantile(-returns, level, method="higher"))


def es_historical(returns: pd.Series, level: float) -> float:
    """Average loss on days worse than the historical VaR."""
    losses = -returns
    var = var_historical(returns, level)
    tail = losses[losses >= var]
    return float(tail.mean()) if len(tail) else var


# --------------------------------------------------------------------------- #
# Parametric (Gaussian)
# --------------------------------------------------------------------------- #
def var_parametric(returns: pd.Series, level: float) -> float:
    mu, sigma = returns.mean(), returns.std(ddof=1)
    z = stats.norm.ppf(level)
    return float(-(mu - z * sigma))


def es_parametric(returns: pd.Series, level: float) -> float:
    mu, sigma = returns.mean(), returns.std(ddof=1)
    z = stats.norm.ppf(level)
    return float(-mu + sigma * stats.norm.pdf(z) / (1 - level))


# --------------------------------------------------------------------------- #
# Monte Carlo (Gaussian draws fitted to the sample; fixed seed = reproducible)
# --------------------------------------------------------------------------- #
def _mc_sample(returns: pd.Series, n: int = 200_000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(returns.mean(), returns.std(ddof=1), size=n)


def var_montecarlo(returns: pd.Series, level: float, n: int = 200_000,
                   seed: int = 42) -> float:
    sim = _mc_sample(returns, n, seed)
    return float(np.quantile(-sim, level))


def es_montecarlo(returns: pd.Series, level: float, n: int = 200_000,
                  seed: int = 42) -> float:
    sim = _mc_sample(returns, n, seed)
    losses = -sim
    var = float(np.quantile(losses, level))
    return float(losses[losses >= var].mean())


# --------------------------------------------------------------------------- #
# EVT: Peaks-Over-Threshold with a Generalised Pareto tail
# --------------------------------------------------------------------------- #
def evt_pot(returns: pd.Series, threshold_q: float = 0.95,
            levels: tuple = (0.95, 0.99, 0.995)) -> dict:
    """
    Fit a GPD to losses above the `threshold_q` quantile.

    Returns the fitted parameters plus VaR/ES at 95/99/99.5% implied by the
    tail model. Threshold justification (mean-excess linearity and parameter
    stability) is exposed through `mean_excess()` for the app/report.
    """
    losses = -returns.dropna()
    u = float(losses.quantile(threshold_q))
    exceed = losses[losses > u] - u
    n, nu = len(losses), len(exceed)
    if nu < 30:
        raise ValueError("Too few exceedances for a stable GPD fit")
    xi, _, beta = stats.genpareto.fit(exceed, floc=0)
    xi, beta = float(xi), float(beta)

    def evt_var(p: float) -> float:
        if p <= threshold_q:
            return var_historical(returns, p)
        if abs(xi) < 1e-8:
            return u + beta * np.log(nu / (n * (1 - p)))
        return u + (beta / xi) * (((n * (1 - p)) / nu) ** (-xi) - 1)

    def evt_es(p: float) -> float:
        if xi >= 1:
            return float("inf")
        v = evt_var(p)
        return (v + beta - xi * u) / (1 - xi) if p > threshold_q else es_historical(returns, p)

    return {
        "threshold": u, "threshold_quantile": threshold_q,
        "n_obs": n, "n_exceedances": int(nu),
        "xi_shape": xi, "beta_scale": beta,
        "var": {p: evt_var(p) for p in levels},
        "es": {p: evt_es(p) for p in levels},
        "tail_type": ("heavy (xi > 0): losses have a fat tail" if xi > 0.02 else
                      "light/exponential-like (xi ~ 0)" if xi >= -0.02 else
                      "bounded (xi < 0)"),
    }


def mean_excess(returns: pd.Series, quantiles=np.arange(0.80, 0.995, 0.01)) -> pd.DataFrame:
    """Mean excess of losses over a grid of thresholds (threshold-choice plot)."""
    losses = -returns.dropna()
    rows = []
    for q in quantiles:
        u = losses.quantile(q)
        exc = losses[losses > u] - u
        rows.append({"quantile": q, "threshold": u,
                     "mean_excess": exc.mean() if len(exc) else np.nan,
                     "n_exceedances": len(exc)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Side-by-side summary used by the app, report and tear sheet
# --------------------------------------------------------------------------- #
def risk_table(returns: pd.Series, levels=(0.95, 0.99)) -> pd.DataFrame:
    """VaR and ES by every method, one tidy table."""
    evt = evt_pot(returns, levels=tuple(levels))
    rows = []
    for lv in levels:
        rows.append({
            "level": lv,
            "VaR_historical": var_historical(returns, lv),
            "VaR_parametric": var_parametric(returns, lv),
            "VaR_montecarlo": var_montecarlo(returns, lv),
            "VaR_evt": evt["var"][lv],
            "ES_historical": es_historical(returns, lv),
            "ES_parametric": es_parametric(returns, lv),
            "ES_montecarlo": es_montecarlo(returns, lv),
            "ES_evt": evt["es"][lv],
        })
    return pd.DataFrame(rows)
