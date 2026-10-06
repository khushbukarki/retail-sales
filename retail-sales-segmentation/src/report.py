"""Run the full analysis: SQL KPIs, RFM segmentation, hypothesis tests, charts and a markdown report.

    python -m src.report                 # uses data/retail.db
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import stats_tests  # noqa: E402
from .db import DEFAULT_DB, ROOT, connect, run_query  # noqa: E402
from .rfm import score_rfm, segment_summary  # noqa: E402

REPORTS = ROOT / "reports"
DASH_DATA = ROOT / "dashboard" / "data"
COLOURS = ["#1f4e79", "#2e75b6", "#5b9bd5", "#9dc3e6", "#c55a11", "#f4b183", "#7f7f7f", "#bfbfbf"]


def chart_monthly(monthly: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(monthly["month"], monthly["revenue"], marker="o", color=COLOURS[0])
    ax.set_title("Monthly revenue")
    ax.set_ylabel("Revenue")
    ax.tick_params(axis="x", rotation=60)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_segments(summary: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    y = range(len(summary))
    ax.barh([i + 0.2 for i in y], summary["customer_share_pct"], height=0.4, label="% of customers", color=COLOURS[3])
    ax.barh([i - 0.2 for i in y], summary["revenue_share_pct"], height=0.4, label="% of revenue", color=COLOURS[0])
    ax.set_yticks(list(y), summary["segment"])
    ax.invert_yaxis()
    ax.set_xlabel("Share (%)")
    ax.set_title("RFM segments: share of customers vs share of revenue")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_rf_heatmap(scored: pd.DataFrame, path: Path):
    grid = scored.pivot_table(index="r_score", columns="f_score", values="monetary", aggfunc="mean")
    grid = grid.reindex(index=[5, 4, 3, 2, 1], columns=[1, 2, 3, 4, 5])
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(grid.values, cmap="Blues")
    ax.set_xticks(range(5), grid.columns)
    ax.set_yticks(range(5), grid.index)
    ax.set_xlabel("Frequency score")
    ax.set_ylabel("Recency score")
    ax.set_title("Average customer spend by R and F score")
    for i in range(5):
        for j in range(5):
            v = grid.values[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=8,
                        color="white" if v > pd.Series(grid.values.ravel()).quantile(0.6) else "black")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(f"{v:,.1f}" if isinstance(v, float) else f"{v:,}" if isinstance(v, int)
                                     else str(v) for v in row) + " |")
    return "\n".join(out)


def build(db_path: Path) -> dict:
    con = connect(db_path)
    kpis = run_query(con, "kpis").iloc[0].to_dict()
    monthly = run_query(con, "monthly_revenue")
    countries = run_query(con, "revenue_by_country")
    products = run_query(con, "top_products")
    repeat = run_query(con, "repeat_customer_rate").iloc[0].to_dict()
    orders = run_query(con, "order_facts")
    scored = score_rfm(run_query(con, "rfm_base"))
    con.close()

    summary = segment_summary(scored)
    tests = stats_tests.run_all(orders, scored)

    (REPORTS / "figures").mkdir(parents=True, exist_ok=True)
    chart_monthly(monthly, REPORTS / "figures" / "monthly_revenue.png")
    chart_segments(summary, REPORTS / "figures" / "rfm_segments.png")
    chart_rf_heatmap(scored, REPORTS / "figures" / "rf_heatmap.png")

    # Small aggregate files for the dashboard (safe to commit; no row-level data)
    DASH_DATA.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(DASH_DATA / "monthly_revenue.csv", index=False)
    countries.to_csv(DASH_DATA / "revenue_by_country.csv", index=False)
    products.to_csv(DASH_DATA / "top_products.csv", index=False)
    summary.to_csv(DASH_DATA / "rfm_segments.csv", index=False)
    pd.DataFrame([t.to_dict() for t in tests]).to_csv(DASH_DATA / "hypothesis_tests.csv", index=False)
    (DASH_DATA / "kpis.json").write_text(json.dumps({**{k: float(v) for k, v in kpis.items()},
                                                     **{k: float(v) for k, v in repeat.items()}}, indent=2))
    scored[["r_score", "f_score", "monetary"]].groupby(["r_score", "f_score"]).mean().round(1).reset_index() \
        .to_csv(DASH_DATA / "rf_grid.csv", index=False)

    write_markdown(kpis, repeat, summary, tests, countries, products)
    return {"kpis": kpis, "segments": summary, "tests": tests, "scored": scored}


def write_markdown(kpis, repeat, summary, tests, countries, products):
    champions = summary.set_index("segment").reindex(["Champions"]).fillna(0).iloc[0]
    at_risk = summary.set_index("segment").reindex(["At risk"]).fillna(0).iloc[0]
    lines = [
        "# Retail Sales Performance & Customer Segmentation – Results",
        "",
        "_Generated by `python -m src.report`. Re-run after loading new data._",
        "",
        "## Headline numbers",
        "",
        f"- **{int(kpis['line_items']):,}** transaction lines across **{int(kpis['orders']):,}** orders "
        f"from **{int(kpis['customers']):,}** customers",
        f"- Revenue **{kpis['revenue']:,.0f}**, average order value **{kpis['avg_order_value']:,.2f}**",
        f"- **{repeat['repeat_rate_pct']}%** of customers ordered more than once",
        f"- Champions are {champions['customer_share_pct']:.1f}% of customers but "
        f"{champions['revenue_share_pct']:.1f}% of revenue; at-risk customers hold "
        f"{at_risk['revenue_share_pct']:.1f}% of revenue",
        "",
        "## Customer segments (RFM)",
        "",
        "![RFM segments](figures/rfm_segments.png)",
        "",
        md_table(summary),
        "",
        "![Recency x frequency heatmap](figures/rf_heatmap.png)",
        "",
        "## What drives order value? (α = 0.05)",
        "",
        "| Hypothesis | Test | Statistic | p-value | Effect | Result |",
        "|---|---|---|---|---|---|",
    ]
    for t in tests:
        lines.append(f"| {t.hypothesis} | {t.test} | {t.statistic} | {t.p_value:.2g} | {t.effect} | "
                     f"{'Significant' if t.significant else 'Not significant'} |")
    lines += ["", *[f"- **{t.hypothesis}:** {t.detail}" for t in tests], ""]
    lines += [
        "With large samples even tiny differences become significant, so read the effect sizes "
        "alongside the p-values.",
        "",
        "## Sales over time",
        "",
        "![Monthly revenue](figures/monthly_revenue.png)",
        "",
        "## Top countries",
        "",
        md_table(countries),
        "",
        "## Top products",
        "",
        md_table(products[["stock_code", "description", "units", "revenue"]]),
        "",
    ]
    (REPORTS / "summary.md").write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    out = build(args.db)
    print(out["segments"].to_string(index=False))
    print()
    for t in out["tests"]:
        print(f"[{'SIG' if t.significant else 'n.s.'}] {t.hypothesis}: {t.effect}, p={t.p_value:.2g}")
    print(f"\nReport written to {REPORTS / 'summary.md'}")


if __name__ == "__main__":
    main()
