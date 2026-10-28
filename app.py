"""
Quant Edge 1.0 - Final Challenge
Serendib University Endowment Fund (USD 10,000,000, conservative mandate)

Streamlit app: portfolio construction, risk dashboard (VaR / ES / EVT),
VaR backtesting, stress testing, and the mandatory
Assumptions & Limitations page.

Run:  streamlit run app.py
Data: data/ (real prices from Yahoo Finance; risk-free from FRED).
      Refresh with:  python scripts/download_data.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from quantedge import backtest, portfolio, risk, stress
from quantedge.data import PORTFOLIO_VALUE, load_all

st.set_page_config(page_title="Quant Edge - Serendib Endowment", layout="wide")

TICKER_NAMES = {
    "SPY": "SPDR S&P 500 ETF (US large-cap equity)",
    "EFA": "iShares MSCI EAFE (developed ex-US equity)",
    "EEM": "iShares MSCI Emerging Markets equity",
    "AGG": "iShares Core US Aggregate Bonds",
    "GLD": "SPDR Gold Shares",
    "XLE": "Energy Select Sector SPDR",
    "XLK": "Technology Select Sector SPDR",
}


# --------------------------------------------------------------------------- #
# Data + cached computations
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def get_data():
    return load_all()


@st.cache_data(show_spinner=False)
def get_candidates(est_years: int):
    d = get_data()
    est = d["simple_returns"].iloc[-est_years * 252:]
    rf_mean = float(d["rf_annual_pct"].reindex(est.index).mean())
    return portfolio.candidate_portfolios(est, rf_mean / 100.0), est


def pct(x: float, dp: int = 2) -> str:
    return f"{x * 100:.{dp}f}%"


def usd(x: float) -> str:
    return f"USD {x:,.0f}"


# --------------------------------------------------------------------------- #
# Sidebar controls (per brief: confidence level, VaR method, backtest range)
# --------------------------------------------------------------------------- #
d = get_data()
simple, rf_daily = d["simple_returns"], d["rf_daily"]
spy = simple["SPY"]

st.sidebar.title("Quant Edge 1.0")
st.sidebar.caption("Serendib University Endowment Fund\nUSD 10,000,000 - conservative mandate")
page = st.sidebar.radio("Section", [
    "Portfolio", "Risk Dashboard (VaR / ES / EVT)", "Backtesting",
    "Stress Testing", "Assumptions & Limitations"])
st.sidebar.divider()
conf = st.sidebar.selectbox("Confidence level", [0.90, 0.95, 0.99], index=2,
                            format_func=lambda v: f"{v:.0%}")
method_label = st.sidebar.selectbox(
    "VaR method (backtesting panel)",
    ["Historical", "Parametric (Gaussian)"])
bt_window = st.sidebar.slider("Backtest rolling window (days)", 125, 500, 250, step=25)
est_years = st.sidebar.slider("Optimisation estimation window (years)", 3, 10, 5)
st.sidebar.caption(f"Data: {simple.index.min().date()} to {simple.index.max().date()} "
                   f"({len(simple):,} trading days, Yahoo Finance adjusted close; "
                   "risk-free: FRED DTB3)")

candidates, est = get_candidates(est_years)
weights = candidates["Recommended (Constrained Min-Var)"]
port = portfolio.portfolio_returns(simple, weights)
est_port = portfolio.portfolio_returns(est, weights)

# --------------------------------------------------------------------------- #
if page == "Portfolio":
    st.title("Recommended Portfolio")
    st.write(
        "The client is a **conservative university endowment**. For this client, "
        "protecting the money is more important than getting the highest return. "
        "So we recommend a **minimum-variance portfolio with extra rules** "
        "(constraints). The rules make sure every asset class stays in the "
        "portfolio and stop the optimiser from putting almost everything into "
        "one or two assets, which is what it does when there are no rules.")

    c1, c2 = st.columns([1, 1.4])
    with c1:
        wdf = pd.DataFrame({
            "Asset": [TICKER_NAMES[t] for t in weights.index],
            "Weight": weights.values,
            "USD": weights.values * PORTFOLIO_VALUE,
        }, index=weights.index)
        st.dataframe(wdf.style.format({"Weight": "{:.1%}", "USD": "USD {:,.0f}"}),
                     width="stretch")
        fig = px.bar(x=weights.index, y=weights.values * 100,
                     labels={"x": "Asset", "y": "Weight (%)"},
                     title="Recommended weights")
        st.plotly_chart(fig, width="stretch")
    with c2:
        k = portfolio.kpis(port, rf_daily, spy)
        m = st.columns(4)
        m[0].metric("CAGR (full history*)", pct(k["CAGR"]))
        m[1].metric("Annual volatility", pct(k["AnnVol"]))
        m[2].metric("Sharpe ratio", f"{k['Sharpe']:.2f}")
        m[3].metric("Max drawdown*", pct(k["MaxDrawdown"]))
        m = st.columns(4)
        m[0].metric("Sortino ratio", f"{k['Sortino']:.2f}")
        m[1].metric("Beta vs SPY", f"{k['Beta_vs_SPY']:.2f}")
        m[2].metric("Jensen's alpha (ann.)", pct(k["JensenAlpha"]))
        m[3].metric("Calmar ratio", f"{k['Calmar']:.2f}")
        st.caption("*Full-history figures apply today's weights to 2007-2026 history "
                   "(hypothetical replay, before fees) - see Assumptions & Limitations.")

        wealth = (1 + port).cumprod() * PORTFOLIO_VALUE
        fig = px.line(x=wealth.index, y=wealth.values / 1e6,
                      labels={"x": "", "y": "Value (USD m)"},
                      title="Growth of USD 10m (hypothetical, today's weights on full history)")
        st.plotly_chart(fig, width="stretch")
        dd = portfolio.drawdown_series(port)
        fig = px.area(x=dd.index, y=dd.values * 100,
                      labels={"x": "", "y": "Drawdown (%)"}, title="Drawdown")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Candidate portfolios compared (full-history performance)")
    rows = {}
    for name, cw in candidates.items():
        pr = portfolio.portfolio_returns(simple, cw)
        kk = portfolio.kpis(pr, rf_daily, spy)
        rows[name] = {"CAGR": pct(kk["CAGR"]), "Vol": pct(kk["AnnVol"]),
                      "Sharpe": f"{kk['Sharpe']:.2f}", "Sortino": f"{kk['Sortino']:.2f}",
                      "MaxDD": pct(kk["MaxDrawdown"]), "Calmar": f"{kk['Calmar']:.2f}"}
    st.dataframe(pd.DataFrame(rows).T, width="stretch")
    st.write("The minimum-variance and maximum-Sharpe portfolios without rules put "
             "almost all the money into a few assets. Our rules version gives up a "
             "little return, but the volatility is about one third lower than the "
             "equal-weight portfolio and the crisis drawdown is much smaller. For "
             "this client, that is the right trade.")

    st.subheader("Where the risk comes from (estimation window)")
    _, cov_a = portfolio.annualised_stats(est)
    rc = portfolio.risk_contributions(weights, cov_a)
    st.dataframe(rc.style.format({"weight": "{:.1%}", "pct_risk": "{:.1f}%"}),
                 width="stretch")
    corr = est.corr()
    fig = px.imshow(corr, zmin=-1, zmax=1, color_continuous_scale="RdYlBu_r",
                    text_auto=".2f", title="Correlation matrix (estimation window)")
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------- #
elif page == "Risk Dashboard (VaR / ES / EVT)":
    st.title("Risk Dashboard - VaR, ES and EVT side by side")
    st.write("Measured on the **estimation window** (recent regime) for the recommended "
             "portfolio. Amounts are 1-day figures on USD 10,000,000.")

    table = risk.risk_table(est_port, levels=(0.90, 0.95, 0.99))
    disp = table.set_index("level").T
    disp.index = [i.replace("_", " ") for i in disp.index]
    st.dataframe(disp.style.format("{:.2%}"), width="stretch")

    lv = conf
    row = table[table["level"] == lv].iloc[0]
    c = st.columns(4)
    c[0].metric(f"VaR {lv:.0%} - Historical", pct(row["VaR_historical"]),
                usd(row["VaR_historical"] * PORTFOLIO_VALUE))
    c[1].metric(f"VaR {lv:.0%} - Parametric", pct(row["VaR_parametric"]),
                usd(row["VaR_parametric"] * PORTFOLIO_VALUE))
    c[2].metric(f"VaR {lv:.0%} - Monte Carlo", pct(row["VaR_montecarlo"]),
                usd(row["VaR_montecarlo"] * PORTFOLIO_VALUE))
    c[3].metric(f"VaR {lv:.0%} - EVT", pct(row["VaR_evt"]),
                usd(row["VaR_evt"] * PORTFOLIO_VALUE))
    c = st.columns(4)
    c[0].metric(f"ES {lv:.0%} - Historical", pct(row["ES_historical"]),
                usd(row["ES_historical"] * PORTFOLIO_VALUE))
    c[1].metric(f"ES {lv:.0%} - Parametric", pct(row["ES_parametric"]),
                usd(row["ES_parametric"] * PORTFOLIO_VALUE))
    c[2].metric(f"ES {lv:.0%} - Monte Carlo", pct(row["ES_montecarlo"]),
                usd(row["ES_montecarlo"] * PORTFOLIO_VALUE))
    c[3].metric(f"ES {lv:.0%} - EVT", pct(row["ES_evt"]),
                usd(row["ES_evt"] * PORTFOLIO_VALUE))

    st.info("**Why do the methods give different numbers?** At 95% the methods are "
            "close to each other. At 99% the Gaussian methods (parametric and Monte "
            "Carlo) give a smaller number than the historical and EVT methods. The "
            "reason is that daily returns have fat tails (excess kurtosis is over 15), "
            "so very bad days happen more often than a normal distribution says. "
            "Because of this, we use the **historical and EVT** numbers for our risk "
            "decisions. We treat the Gaussian number as a lower bound only.")

    st.subheader("EVT - Peaks over Threshold (Generalised Pareto tail)")
    evt = risk.evt_pot(est_port)
    c = st.columns(4)
    c[0].metric("Threshold u (95th pct of losses)", pct(evt["threshold"]))
    c[1].metric("Exceedances", f"{evt['n_exceedances']} of {evt['n_obs']}")
    c[2].metric("Shape xi", f"{evt['xi_shape']:.3f}")
    c[3].metric("Scale beta", pct(evt["beta_scale"]))
    st.write(f"Tail diagnosis: **{evt['tail_type']}**. A positive xi means the loss tail "
             "decays like a power law, not an exponential - extreme losses are more likely "
             "than a normal model admits, which is exactly why the EVT VaR exceeds the "
             "parametric VaR at 99%.")
    me = risk.mean_excess(est_port)
    fig = px.scatter(me, x=me["threshold"] * 100, y=me["mean_excess"] * 100,
                     labels={"x": "Threshold u (% daily loss)", "y": "Mean excess (%)"},
                     title="Mean-excess plot - roughly linear above the 95th percentile, "
                           "supporting the chosen threshold")
    st.plotly_chart(fig, width="stretch")
    losses = -est_port
    fig = px.histogram(losses * 100, nbins=80,
                       labels={"value": "Daily loss (%)"},
                       title="Distribution of daily losses (estimation window)")
    fig.add_vline(x=row["VaR_historical"] * 100, line_color="red",
                  annotation_text=f"Historical VaR {lv:.0%}")
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------- #
elif page == "Backtesting":
    st.title("VaR Backtesting")
    method = "historical" if method_label == "Historical" else "parametric"
    st.write(f"Rolling {bt_window}-day **{method_label}** VaR at **{conf:.0%}**, "
             "forecast one day ahead over the full history. An exception is a day whose "
             "realised loss exceeded the VaR forecast.")
    res = backtest.backtest_summary(port, level=conf, window=bt_window, method=method)
    bt = res.pop("series")
    c = st.columns(4)
    c[0].metric("Observations", f"{res['n_obs']:,}")
    c[1].metric("Exceptions", f"{res['exceptions']} (expected {res['kupiec']['expected']:.0f})")
    c[2].metric("Kupiec POF p-value", f"{res['kupiec']['p_value']:.3f}",
                "reject" if res["kupiec"]["reject_at_5pct"] else "not rejected")
    c[3].metric("Basel zone (last 250)", res["basel_last_250"]["zone"])
    ch = res["christoffersen"]
    st.write(f"**Christoffersen independence:** LR = {ch['LR_independence']:.2f}, "
             f"p = {ch['p_independence']:.3f} - "
             + ("exceptions **cluster** (volatility regimes), so the model fails the "
                "independence test even where coverage is close."
                if ch["p_independence"] < 0.05 else
                "no significant evidence that exceptions cluster.")
             + f" **Conditional coverage:** p = {ch['p_conditional_coverage']:.3f}.")
    st.write("**How to read this:** over the full 19 years, the 99% VaR models do not "
             "pass the tests. The exceptions come in groups during crises, because a "
             "250-day window changes slowly and a crisis moves fast. The historical "
             "model is closer to the correct number than the parametric model, and in "
             "the last 250 days the traffic light is green or yellow. Our conclusion: "
             "use VaR for normal day-to-day sizing, but control the fund with ES and "
             "stress limits, not with VaR alone.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bt.index, y=-bt["return"] * 100, mode="lines",
                             name="Daily loss (%)", line=dict(width=0.7)))
    fig.add_trace(go.Scatter(x=bt.index, y=bt["VaR"] * 100, mode="lines",
                             name=f"VaR {conf:.0%} (%)", line=dict(color="red", width=0.9)))
    exc = bt[bt["exception"] == 1]
    fig.add_trace(go.Scatter(x=exc.index, y=-exc["return"] * 100, mode="markers",
                             name="Exception", marker=dict(color="red", size=5, symbol="x")))
    fig.update_layout(title="Rolling VaR vs realised losses", yaxis_title="%")
    st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------------- #
elif page == "Stress Testing":
    st.title("Stress Testing")
    st.subheader("Historical replays - today's weights on crisis windows")
    rep = stress.historical_replay(simple, weights, PORTFOLIO_VALUE)
    show = rep[["scenario", "window", "portfolio_return", "portfolio_loss_usd",
                "max_drawdown_in_window"]].copy()
    show.columns = ["Scenario", "Window", "Portfolio return", "Loss (USD)",
                    "Max drawdown in window"]
    st.dataframe(show.style.format({"Portfolio return": "{:.2%}",
                                    "Loss (USD)": "USD {:,.0f}",
                                    "Max drawdown in window": "{:.2%}"}),
                 width="stretch")
    st.caption("A replay, not a record: this portfolio was not held in 2008. The question "
               "answered is 'what would today's mix have done then?' Asset-level returns "
               "for each window are in the technical report.")

    st.subheader("Hypothetical scenario - 'Stagflation shock, bonds fail to protect'")
    st.write("This is the bad scenario we designed ourselves. Inflation goes up again "
             "and central banks raise rates when the economy is already slow. Stocks "
             "fall a lot. **AGG also falls**, because inflation is the problem, so the "
             "bond protection does not work - the same thing that happened in 2022, "
             "but stronger. Gold goes up. The shocks below are total moves over about "
             "6 months. You can change them and the Monte Carlo result will change.")
    cols = st.columns(4)
    shocks = {}
    defaults = stress.HYPOTHETICAL_SHOCKS
    for i, t in enumerate(weights.index):
        shocks[t] = cols[i % 4].number_input(f"{t} shock (%)",
                                             value=float(defaults[t] * 100),
                                             step=1.0, format="%.1f") / 100.0
    hyp = stress.hypothetical_mc(simple, weights, shocks=shocks)
    c = st.columns(4)
    c[0].metric("Deterministic impact", pct(hyp["deterministic_portfolio_impact"]),
                usd(-hyp["deterministic_loss_usd"]) if hyp["deterministic_portfolio_impact"] < 0 else "gain")
    c[1].metric("MC 95% loss", pct(hyp["mc_var95_loss"]),
                usd(hyp["mc_var95_loss"] * PORTFOLIO_VALUE))
    c[2].metric("MC 99% loss", pct(hyp["mc_var99_loss"]),
                usd(hyp["mc_var99_loss"] * PORTFOLIO_VALUE))
    c[3].metric("P(loss worse than 10%)", f"{hyp['prob_loss_gt_10pct']:.0%}")
    st.write("Even in this bad scenario, the fund loses about one tenth of its value "
             "on the deterministic path. That is painful, but the fund can survive it, "
             "and it is much better than a portfolio with mostly stocks. The reason is "
             "that 60% of the money is in bonds and gold, and the gold shock is "
             "positive. The Monte Carlo part uses correlations of 0.85 inside the "
             "stock group, because in a crisis stocks start to move together. That "
             "shows the worse cases.")

# --------------------------------------------------------------------------- #
else:
    st.title("Assumptions & Limitations")
    st.markdown("""
### Data
- Prices are **Yahoo Finance adjusted closes** (dividends and splits reinvested), aligned
  on the common US trading calendar, 3 Jan 2007 - 28 Oct 2026 (4,987 days). The risk-free
  rate is the FRED 3-month T-bill (DTB3). Suspected data errors were **flagged, not
  deleted** (see `data/data_quality_report.json`); log-return series pass ADF
  stationarity tests at 5% for all seven assets.
- ETF prices are used as proxies for asset classes; tracking error, fees and bid-ask
  spreads are ignored. Past prices say nothing certain about the future.

### Model assumptions
- **Optimisation** uses a trailing 5-year window with Ledoit-Wolf shrunk covariance.
  For our recommendation we do not use the estimated mean returns at all
  (minimum-variance only needs the covariances). This is because means are
  estimated with much more error than covariances.
- **Historical VaR** assumes that the distribution of the past window will repeat.
  **Parametric VaR** and the Gaussian **Monte Carlo** assume returns are normal.
  This is not true in the tails (excess kurtosis is over 15), so we report those
  numbers as a lower bound, not as the main risk number.
- **EVT/POT** assumes the exceedances above the threshold follow a Generalised Pareto
  distribution and are roughly independent. In real data, volatility comes in
  clusters, so this is not exactly true. Because of that, we cross-check the EVT
  numbers against the historical ES.
- **Backtests** use today's fixed weights on the whole history. This is a replay.
  A real fund would have rebalanced, and the weights in 2008 would not be the
  same as today.
- The stress replays are also hypothetical. The designed scenario is our own
  judgement, not a forecast. In the Monte Carlo scenario we set the correlations
  inside the stock group to 0.85 by hand, because correlations go up in a crisis.
- We did not model transaction costs, taxes, liquidity or market impact.
  All numbers are 1-day numbers unless we say otherwise. We do not use the
  square-root-of-time rule anywhere without saying it.

### What would change our conclusions
- A structural break in the bond-equity correlation (a long inflationary regime makes
  AGG a weaker hedge - the 2022 replay and the designed scenario both probe this).
- A gold regime change: GLD is 20% of the fund and carries much of the crisis offset.
- Estimation-window choice: weights were re-derived on 3- and 10-year windows; the
  defensive tilt (AGG + GLD >= 55%) is stable, exact weights are not.

### AI-use disclosure (per competition rules)
| Tool | Purpose | Human validation | Material AI component |
|---|---|---|---|
| AI assistant (Muse) | Code drafting, debugging, report structure | Every figure recomputed from the saved data files; formulas checked against the cited literature; results cross-validated between the analysis scripts and this app | Code scaffolding and text drafting only - no AI-generated data, no AI-chosen conclusions |
| Yahoo Finance / FRED | Market and risk-free data | Adjusted-close methodology documented; ADF and data-quality checks in `data/data_quality_report.json` | None |

All investment judgements - the conservative constraints, the scenario design, and the
recommendation itself - are the team's own and are defended as such in the pitch.
""")
