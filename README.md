# Quant Edge 1.0 - Final Challenge

Team n0T4ounD, Sabaragamuwa University of Sri Lanka.

This is our project for the Quant Edge 1.0 final challenge. The client is the
Serendib University Endowment Fund. The fund has USD 10,000,000 and a
conservative mandate, which means protecting the money comes first and
return comes second. Our job was to build a portfolio for this fund, measure
its risk properly, test the risk models, and show what happens to the
portfolio in a crisis.

The app is a Streamlit app. Anyone can open it and check our numbers.

## Run the app

```
pip install -r requirements.txt
streamlit run app.py
```

The app works with the data files in this repo, so no internet or API key is
needed to run it.

## What the app does

- **Portfolio page** - the weights we recommend, the candidate portfolios we
  compared them with, and the main performance numbers (Sharpe, Sortino,
  drawdown, beta, Jensen's alpha and the others the brief asked for).
- **Risk dashboard** - VaR and Expected Shortfall from three methods
  (historical, parametric, Monte Carlo) plus EVT, side by side at 95% and 99%.
- **Backtesting page** - Kupiec and Christoffersen tests and the Basel
  traffic light for our VaR models.
- **Stress testing page** - what our portfolio would have done in 2008, in
  the 2020 COVID crash and in 2022, plus one bad scenario we designed
  ourselves (stagflation).
- **Assumptions and limitations page** - what we assumed, where the models
  can go wrong, and the AI-use disclosure table the rules ask for.

## Our recommended portfolio

| Asset | Weight |
|---|---|
| SPY (US stocks) | 13.3% |
| EFA (developed markets) | 5.5% |
| EEM (emerging markets) | 5.0% |
| AGG (US bonds) | 40.0% |
| GLD (gold) | 20.0% |
| XLE (energy) | 11.2% |
| XLK (technology) | 5.0% |

It is a minimum-variance portfolio with some rules on top (no asset below
5% or above 40%, at least 25% in bonds, at most 60% in stocks, at most 20%
in gold). We did not use the plain minimum-variance or maximum-Sharpe
portfolios because they put almost everything into one or two assets. The
full comparison is in the report and in the app.

## Main risk numbers (1-day, recent 5-year window)

| | 95% | 99% |
|---|---|---|
| VaR, historical | 0.89% | 1.57% |
| VaR, parametric | 0.92% | 1.32% |
| VaR, EVT | 0.89% | 1.57% |
| ES, historical | 1.32% | 2.05% |

The important point: at 99% the normal-distribution methods give a smaller
number than the methods that use the real data. Daily returns have fat
tails, so the Gaussian number is too optimistic. We used the historical and
EVT numbers for our risk decisions. The EVT tail index came out at
xi = +0.06, which also says the tail is a bit heavy.

In the backtests, the 95% VaR models passed the Kupiec test, but the 99%
models did not pass over the full 2007-2026 period, because the exceptions
come in groups during crises. This is why we say in the report that the fund
should be controlled with ES and stress limits, not with VaR alone.

## Data

All the data is real. Prices are adjusted close prices from Yahoo Finance
for SPY, EFA, EEM, AGG, GLD, XLE and XLK, from January 2007 to October 2026
(4,987 trading days). The risk-free rate is the 3-month T-bill from FRED.
We aligned all the calendars, used log returns for the statistics, and
checked every series with an ADF test (all stationary). Data problems were
flagged, not deleted - see `data/data_quality_report.json`.

To download the data again and re-run everything:

```
python scripts/download_data.py
python scripts/run_analysis.py
```

## Files

```
app.py            the Streamlit app
quantedge/        all the calculations (portfolio, risk, backtest, stress)
data/             the cleaned data files
scripts/          download_data.py and run_analysis.py
results/          results.json and the result tables (charts are in the report)
report/           the written report and the one-page tear sheet
```

One honest note: the full-history performance numbers use today's weights
on old data. The portfolio did not exist in 2008, so those numbers are a
replay to test the mix, not a real track record. We have written this in
the report and in the app as well.
