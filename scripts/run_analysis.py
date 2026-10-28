"""
Run the full analysis on the recommended portfolio and write every number
the Streamlit app, the report and the tear sheet need into results/.

Single source of truth: app + report + tear sheet all read results.json.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from quantedge import backtest, portfolio, risk, stress
from quantedge.data import PORTFOLIO_VALUE, load_all

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)
EST_YEARS = 5  # optimisation estimation window: trailing 5 years

plt.rcParams.update({"figure.dpi": 130, "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False})


def jclean(o):
    if isinstance(o, dict):
        return {k: jclean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jclean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def main() -> None:
    d = load_all()
    simple, logr = d["simple_returns"], d["log_returns"]
    rf_daily, rf_pct = d["rf_daily"], d["rf_annual_pct"]
    spy = simple["SPY"]

    # ---------------- portfolio construction --------------------------------
    est = simple.iloc[-EST_YEARS * 252:]
    rf_ann_est = float(rf_pct.reindex(est.index).mean() / 100.0)
    cands = portfolio.candidate_portfolios(est, rf_ann_est)
    rec_name = "Recommended (Constrained Min-Var)"
    w = cands[rec_name]

    results: dict = {"meta": {
        "portfolio_value": PORTFOLIO_VALUE,
        "data_start": str(simple.index.min().date()),
        "data_end": str(simple.index.max().date()),
        "n_obs": int(len(simple)),
        "estimation_window": f"{est.index.min().date()} to {est.index.max().date()}",
        "recommended": rec_name,
        "weights": {k: float(v) for k, v in w.items()},
    }}

    # ---------------- candidates compared on FULL history --------------------
    cand_rows = {}
    for name, cw in cands.items():
        pr = portfolio.portfolio_returns(simple, cw)
        k = portfolio.kpis(pr, rf_daily, spy)
        cand_rows[name] = {**{kk: float(vv) for kk, vv in cw.items()},
                           **{f"kpi_{kk}": vv for kk, vv in k.items()}}
    cand_df = pd.DataFrame(cand_rows).T
    cand_df.to_csv(OUT / "candidates.csv")
    results["candidates"] = jclean(cand_rows)

    # ---------------- recommended portfolio analytics ------------------------
    port = portfolio.portfolio_returns(simple, w)
    results["kpis_full_history"] = jclean(portfolio.kpis(port, rf_daily, spy))
    est_port = portfolio.portfolio_returns(est, w)
    results["kpis_estimation_window"] = jclean(portfolio.kpis(est_port, rf_daily, spy))

    mu_a, cov_a = portfolio.annualised_stats(est)
    rc = portfolio.risk_contributions(w, cov_a)
    rc.to_csv(OUT / "risk_contributions.csv")
    results["risk_contributions"] = jclean(rc.round(4).to_dict("index"))
    results["correlation"] = jclean(est.corr().round(3).to_dict())
    results["asset_stats"] = jclean(pd.DataFrame({
        "ann_return": est.mean() * 252, "ann_vol": est.std() * np.sqrt(252),
        "worst_day": est.min(), "skew": est.skew(), "kurtosis": est.kurtosis(),
    }).round(4).to_dict("index"))

    # ---------------- risk: VaR / ES / EVT -----------------------------------
    # Risk numbers are measured on the estimation window (current regime) AND
    # on full history; the report discusses both.
    rt_est = risk.risk_table(est_port)
    rt_full = risk.risk_table(port)
    rt_est.to_csv(OUT / "risk_table_estimation.csv", index=False)
    rt_full.to_csv(OUT / "risk_table_full.csv", index=False)
    results["risk_table_estimation"] = jclean(rt_est.round(5).to_dict("records"))
    results["risk_table_full"] = jclean(rt_full.round(5).to_dict("records"))
    evt = risk.evt_pot(est_port)
    results["evt"] = jclean({k: v for k, v in evt.items()})
    me = risk.mean_excess(est_port)
    me.to_csv(OUT / "mean_excess.csv", index=False)

    # ---------------- backtesting --------------------------------------------
    bt_out = {}
    for method in ("historical", "parametric"):
        for level in (0.99, 0.95):
            s = backtest.backtest_summary(port, level=level, window=250, method=method)
            s.pop("series").to_csv(OUT / f"backtest_{method}_{int(level*100)}.csv")
            bt_out[f"{method}_{int(level*100)}"] = jclean(
                {k: v for k, v in s.items() if k != "series"})
    results["backtests"] = bt_out

    # ---------------- stress ---------------------------------------------------
    replays = stress.historical_replay(simple, w, PORTFOLIO_VALUE)
    replays.to_csv(OUT / "stress_replays.csv", index=False)
    results["stress_replays"] = jclean(replays.round(4).to_dict("records"))
    hyp = stress.hypothetical_mc(simple, w)
    results["stress_hypothetical"] = jclean(hyp)

    # ---------------- charts ---------------------------------------------------
    wealth = (1 + port).cumprod() * PORTFOLIO_VALUE
    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    ax.plot(wealth.index, wealth.values / 1e6, lw=1.1, color="#1f4e79")
    ax.set_ylabel("Portfolio value (USD m)")
    ax.set_title("Growth of USD 10m - recommended weights applied to full history (hypothetical, before fees)")
    fig.tight_layout(); fig.savefig(OUT / "growth.png"); plt.close(fig)

    dd = portfolio.drawdown_series(port)
    fig, ax = plt.subplots(figsize=(8.5, 2.8))
    ax.fill_between(dd.index, dd.values * 100, 0, color="#b23a48", alpha=.75)
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("Drawdown of the recommended portfolio (full history, hypothetical)")
    fig.tight_layout(); fig.savefig(OUT / "drawdown.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar(w.index, w.values * 100, color="#1f4e79")
    ax.set_ylabel("Weight (%)"); ax.set_title("Recommended portfolio weights")
    fig.tight_layout(); fig.savefig(OUT / "weights.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    ax.plot(me["threshold"] * 100, me["mean_excess"] * 100, marker="o", ms=3, color="#1f4e79")
    ax.set_xlabel("Threshold u (% daily loss)"); ax.set_ylabel("Mean excess (%)")
    ax.set_title("Mean-excess plot (EVT threshold choice)")
    fig.tight_layout(); fig.savefig(OUT / "mean_excess.png"); plt.close(fig)

    corr = est.corr()
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    im = ax.imshow(corr, cmap="RdYlBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=45)
    ax.set_yticks(range(len(corr)), corr.columns)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7.5)
    fig.colorbar(im, shrink=.85); ax.set_title("Correlation matrix (estimation window)")
    fig.tight_layout(); fig.savefig(OUT / "correlation.png"); plt.close(fig)

    (OUT / "results.json").write_text(json.dumps(jclean(results), indent=2))
    print("weights:", {k: round(v, 4) for k, v in w.items()})
    print("KPI full:", {k: round(v, 4) for k, v in results["kpis_full_history"].items()})
    print("EVT xi:", round(evt["xi_shape"], 3), "beta:", round(evt["beta_scale"], 5))
    print("risk table (est):"); print(rt_est.round(4).to_string(index=False))
    for k, v in bt_out.items():
        print(k, "exceptions:", v["exceptions"], "/", v["n_obs"],
              "Kupiec p:", round(v["kupiec"]["p_value"], 3),
              "Basel250:", v["basel_last_250"]["zone"])
    print(replays[["scenario", "portfolio_return", "max_drawdown_in_window"]].round(4).to_string(index=False))
    print("hypothetical:", {k: (round(v, 4) if isinstance(v, float) else v)
                            for k, v in hyp.items() if k != "shocks"})


if __name__ == "__main__":
    main()
