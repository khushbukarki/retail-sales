"""Streamlit dashboard. Reads the small aggregate files written by `python -m src.report`,
so it can be deployed (e.g. Streamlit Community Cloud) without the raw transaction data."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data"
st.set_page_config(page_title="Retail sales & customer segments", layout="wide")

if not (DATA / "kpis.json").exists():
    st.error("No results yet. Run `python -m src.load_data` and `python -m src.report`, then reload.")
    st.stop()

kpis = json.loads((DATA / "kpis.json").read_text())
monthly = pd.read_csv(DATA / "monthly_revenue.csv")
segments = pd.read_csv(DATA / "rfm_segments.csv")
tests = pd.read_csv(DATA / "hypothesis_tests.csv")
countries = pd.read_csv(DATA / "revenue_by_country.csv")
products = pd.read_csv(DATA / "top_products.csv")
grid = pd.read_csv(DATA / "rf_grid.csv")

st.title("Retail sales performance & customer segmentation")
st.caption("SQL data model → RFM segmentation → hypothesis testing. Source code on GitHub.")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Transaction lines", f"{kpis['line_items']:,.0f}")
c2.metric("Orders", f"{kpis['orders']:,.0f}")
c3.metric("Customers", f"{kpis['customers']:,.0f}")
c4.metric("Avg order value", f"{kpis['avg_order_value']:,.2f}")
c5.metric("Repeat customers", f"{kpis['repeat_rate_pct']:.1f}%")

tab_seg, tab_tests, tab_sales = st.tabs(["Customer segments", "What drives order value", "Sales"])

with tab_seg:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Share of customers vs share of revenue")
        st.bar_chart(segments.set_index("segment")[["customer_share_pct", "revenue_share_pct"]], horizontal=True)
    with right:
        st.subheader("Average spend by R and F score")
        pivot = grid.pivot(index="r_score", columns="f_score", values="monetary").sort_index(ascending=False)
        st.dataframe(pivot.style.background_gradient(cmap="Blues").format("{:,.0f}"), use_container_width=True)
    st.dataframe(segments, hide_index=True, use_container_width=True)

    chosen = st.selectbox("Suggested action for a segment", segments["segment"])
    actions = {
        "Champions": "Reward and retain: early access, referral programme, avoid unnecessary discounts.",
        "Loyal": "Upsell higher-value ranges and invite to loyalty tiers.",
        "Potential loyalists": "Nudge toward a second and third order with personalised recommendations.",
        "New customers": "Onboarding sequence and a reason to come back within 30 days.",
        "Needs attention": "Time-limited offers based on past purchases before they lapse.",
        "At risk": "Win-back campaign: these customers used to buy often and hold real revenue.",
        "About to sleep": "Low-cost reactivation email; don't over-invest.",
        "Hibernating": "Include only in broad campaigns; focus spend elsewhere.",
    }
    st.info(actions.get(chosen, ""))

with tab_tests:
    st.write("Group comparisons use Welch's t-test on log order value (order values are heavily skewed). "
             "Large samples make small effects significant, so check the effect size column too.")
    show = tests.assign(result=tests["significant"].map({True: "Significant", False: "Not significant"}))
    st.dataframe(show[["hypothesis", "test", "statistic", "p_value", "effect", "result"]],
                 hide_index=True, use_container_width=True)
    for _, row in tests.iterrows():
        st.markdown(f"**{row['hypothesis']}** — {row['detail']}")

with tab_sales:
    st.subheader("Monthly revenue")
    st.line_chart(monthly.set_index("month")["revenue"])
    a, b = st.columns(2)
    a.subheader("Top countries")
    a.dataframe(countries, hide_index=True, use_container_width=True)
    b.subheader("Top products")
    b.dataframe(products[["description", "units", "revenue"]], hide_index=True, use_container_width=True)
