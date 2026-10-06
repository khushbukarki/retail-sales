"""RFM (recency, frequency, monetary) scoring and rule-based customer segments."""
import pandas as pd

# Segment rules on (R score, F score), checked in order. Scores are 1 (worst) to 5 (best).
SEGMENT_RULES = [
    ("Champions",           lambda r, f: r >= 4 and f >= 4),
    ("Loyal",               lambda r, f: r >= 3 and f >= 4),
    ("Potential loyalists", lambda r, f: r >= 4 and f >= 2),
    ("New customers",       lambda r, f: r >= 4 and f == 1),
    ("Needs attention",     lambda r, f: r == 3 and f >= 2),
    ("At risk",             lambda r, f: r <= 2 and f >= 3),
    ("About to sleep",      lambda r, f: r == 3 and f == 1),
    ("Hibernating",         lambda r, f: r <= 2 and f <= 2),
]
SEGMENT_ORDER = [name for name, _ in SEGMENT_RULES]


def quintile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Score 1-5 by percentile rank. Ranking first avoids qcut failing on tied values
    (most customers have frequency 1)."""
    pct = series.rank(method="average", pct=True, ascending=higher_is_better)
    return pd.cut(pct, bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0], labels=[1, 2, 3, 4, 5], include_lowest=True).astype(int)


def assign_segment(r: int, f: int) -> str:
    for name, rule in SEGMENT_RULES:
        if rule(r, f):
            return name
    return "Other"


def score_rfm(rfm: pd.DataFrame) -> pd.DataFrame:
    """rfm needs columns customer_id, recency_days, frequency, monetary."""
    out = rfm.copy()
    out["r_score"] = quintile_score(out["recency_days"], higher_is_better=False)
    out["f_score"] = quintile_score(out["frequency"])
    out["m_score"] = quintile_score(out["monetary"])
    out["rfm_code"] = out["r_score"].astype(str) + out["f_score"].astype(str) + out["m_score"].astype(str)
    out["segment"] = [assign_segment(r, f) for r, f in zip(out["r_score"], out["f_score"])]
    return out


def segment_summary(scored: pd.DataFrame) -> pd.DataFrame:
    total_rev = scored["monetary"].sum()
    s = (
        scored.groupby("segment")
        .agg(customers=("customer_id", "count"),
             avg_recency_days=("recency_days", "mean"),
             avg_orders=("frequency", "mean"),
             avg_spend=("monetary", "mean"),
             revenue=("monetary", "sum"))
        .reindex([x for x in SEGMENT_ORDER if x in set(scored["segment"])])
    )
    s["customer_share_pct"] = 100 * s["customers"] / s["customers"].sum()
    s["revenue_share_pct"] = 100 * s["revenue"] / total_rev
    return s.round(1).reset_index()
