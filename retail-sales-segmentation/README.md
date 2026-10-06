# Retail Sales Performance & Customer Segmentation

End-to-end analysis of an online retailer's transactions: a **normalised SQL data model**, **RFM customer segmentation**, and **statistical tests** of what drives order value, published as an interactive **Streamlit dashboard**.

**Live dashboard:** `https://<your-app>.streamlit.app` · **Full results:** [reports/summary.md](reports/summary.md)

![RFM segments](reports/figures/rfm_segments.png)

## Questions answered

1. Which customers drive revenue, and which valuable customers are drifting away?
2. Do international orders differ in value from domestic ones?
3. Is the Oct–Dec peak about more orders, or bigger orders?
4. Do wider baskets, and more frequent customers, mean higher spend per order?

## Approach

**Data model.** The raw export is one flat table where every line repeats the customer, country and product description. It is normalised into five related tables (`countries`, `customers`, `products`, `invoices`, `invoice_lines`) with primary/foreign keys, `CHECK` constraints and indexes (`sql/schema.sql`). Analysis queries in `sql/analysis_queries.sql` use joins, CTEs and window functions.

**Cleaning** (`src/load_data.py`) removes rows with no customer ID, cancelled invoices (prefixed `C`), non-positive quantities or prices, non-product codes such as postage and bank charges, and exact duplicates. Every step is counted in a cleaning log. Customers listed under several countries get their most frequent one; product descriptions use the most common wording per stock code.

**RFM segmentation** (`src/rfm.py`). Recency, frequency and monetary value are scored 1–5 by percentile rank (ranking first avoids quantile binning breaking on the many customers with exactly one order), and recency/frequency scores map to eight segments from *Champions* to *Hibernating*.

**Hypothesis testing** (`src/stats_tests.py`). Order values are heavily right-skewed, so group comparisons use **Welch's t-test** on log order value (no equal-variance assumption), reporting Cohen's d and a 95% CI for the ratio of typical order values. Relationships use **Pearson correlation** on log-log values with a Fisher-z confidence interval. With samples this large almost anything is "significant", so the report leads with effect sizes.

## Results

Run the pipeline and the headline numbers, segment table and test results are written to [`reports/summary.md`](reports/summary.md). Copy the key findings here, for example:

- _Champions are X% of customers but Y% of revenue._
- _At-risk customers hold Z% of revenue — the clearest win-back target._
- _International orders are typically N× the size of domestic ones (Welch's t, d = …)._

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

1. **Get the data:** download *Online Retail II* from the [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii) and save the `.xlsx` in `data/`. (No data handy? `python -m src.load_data --synthetic` generates realistic demo data so you can try the pipeline.)
2. **Build the database:** `python -m src.load_data --input data/online_retail_II.xlsx`
3. **Run the analysis:** `python -m src.report` → charts in `reports/figures/`, write-up in `reports/summary.md`, dashboard data in `dashboard/data/`
4. **Open the dashboard:** `streamlit run dashboard/app.py`

The SQL queries can also be run directly: `sqlite3 data/retail.db < sql/analysis_queries.sql`.

### Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests check the cleaning rules, foreign-key integrity, that every named SQL query runs, that revenue reconciles across three independent queries, the RFM scoring edge cases, and that the t-test detects a planted difference but not a non-difference.

## Deploy the dashboard (free)

1. Run steps 1–3 above so `dashboard/data/` contains your results, then commit and push. Only small aggregate CSVs are committed; the raw data and database stay out of git.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, choose **New app**, pick this repo and set the main file to `dashboard/app.py`.
3. Put the resulting link at the top of this README and on your CV.

## Project structure

```
sql/schema.sql              5-table normalised model
sql/analysis_queries.sql    named KPI, segmentation and fact queries
src/load_data.py            cleaning + normalisation + synthetic data generator
src/rfm.py                  RFM scoring and segment rules
src/stats_tests.py          Welch's t-test, Pearson correlation, effect sizes
src/report.py               runs everything, charts, markdown report, dashboard data
dashboard/app.py            Streamlit dashboard
tests/                      pytest suite
```
