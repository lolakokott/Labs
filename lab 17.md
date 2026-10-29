# Lab 17 — DGS10 Point-in-Time Audit

**Series:** DGS10 — 10-Year Treasury Constant Maturity Rate

**Source:** Board of Governors of the Federal Reserve System, H.15 Selected Interest Rates, accessed through FRED.

**Link:** https://fred.stlouisfed.org/series/DGS10

**Measure:** The market yield on U.S. Treasury securities with a constant maturity of 10 years.

**Units:** Percent per annum, not seasonally adjusted.

**Frequency and publication lag:** Daily on business days, generally published the following business day.

**Revisions:** The app found zero revised observations when comparing the September 30, 2026 vintage with current data. This does not guarantee the series is never revised.

**Download date:** October 29, 2026.

### Point-in-Time Results

- As of September 30, 2026, the latest available observation was September 29, at 5.26%.
- As of October 29, 2026, the latest observation was October 28, at 5.05%.
- There were 20 additional observations and zero revisions in the app's comparison.

### Three FRED Values Checked Manually

1. October 26, 2026 — 5.00%

2. October 27, 2026 — 4.99%

3. October 28, 2026 — 5.05%

### Partner Attack

**Concern:** How can we be sure DGS10 values were available on the dates used in the backtest?

**Response:** My app showed that as of September 30, 2026, the most recent available DGS10 observation was from September 29, 2026, with a yield of 5.26%. This demonstrates that the series has a publication lag, so Project 2 must use only observations available as of each trading decision date to avoid look-ahead bias.

### Project 2 Decision — Admit

I would admit DGS10 into Project 2 because it has a short publication lag and no revisions detected in my test. However, the backtest must use only observations available as of each trading decision date. Using today's complete historical data would introduce look-ahead bias. I would reconsider admission if additional testing reveals revisions or publication delays that the backtest cannot handle.
