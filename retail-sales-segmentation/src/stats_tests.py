"""Hypothesis tests for what drives order value.

Order values are heavily right-skewed, so group comparisons use log(order value) with Welch's
t-test (no equal-variance assumption) and report Cohen's d and a 95% CI for the difference.
"""
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class TestResult:
    test: str
    hypothesis: str
    statistic: float
    p_value: float
    effect: str
    detail: str
    significant: bool

    def to_dict(self):
        return asdict(self)


def welch_test(a: pd.Series, b: pd.Series, label_a: str, label_b: str, hypothesis: str,
               alpha: float = 0.05) -> TestResult:
    la, lb = np.log(a.to_numpy()), np.log(b.to_numpy())
    t, p = stats.ttest_ind(la, lb, equal_var=False)
    # Welch-Satterthwaite CI on the difference of log means
    va, vb = la.var(ddof=1) / len(la), lb.var(ddof=1) / len(lb)
    dof = (va + vb) ** 2 / (va**2 / (len(la) - 1) + vb**2 / (len(lb) - 1))
    diff = la.mean() - lb.mean()
    half = stats.t.ppf(0.975, dof) * np.sqrt(va + vb)
    pooled_sd = np.sqrt((la.var(ddof=1) + lb.var(ddof=1)) / 2)
    d = diff / pooled_sd
    ratio, lo, hi = np.exp(diff), np.exp(diff - half), np.exp(diff + half)
    return TestResult(
        test="Welch's t-test (log order value)",
        hypothesis=hypothesis,
        statistic=round(float(t), 3),
        p_value=float(p),
        effect=f"Cohen's d = {d:.2f}",
        detail=(f"{label_a}: median {a.median():,.0f} (n={len(a):,}); {label_b}: median {b.median():,.0f} "
                f"(n={len(b):,}). Typical {label_a} order is {ratio:.2f}x {label_b} (95% CI {lo:.2f}-{hi:.2f})."),
        significant=bool(p < alpha),
    )


def pearson_test(x: pd.Series, y: pd.Series, hypothesis: str, log: bool = True, alpha: float = 0.05) -> TestResult:
    xv, yv = (np.log(x), np.log(y)) if log else (x, y)
    r, p = stats.pearsonr(xv, yv)
    # Fisher z 95% CI for r
    z, se = np.arctanh(r), 1 / np.sqrt(len(xv) - 3)
    lo, hi = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
    return TestResult(
        test="Pearson correlation" + (" (log-log)" if log else ""),
        hypothesis=hypothesis,
        statistic=round(float(r), 3),
        p_value=float(p),
        effect=f"r = {r:.2f}, r² = {r*r:.2f}",
        detail=f"95% CI for r: {lo:.2f} to {hi:.2f}, n = {len(xv):,}.",
        significant=bool(p < alpha),
    )


def run_all(orders: pd.DataFrame, rfm: pd.DataFrame, home_country: str | None = None) -> list[TestResult]:
    """orders: one row per order (see the order_facts query). rfm: one row per customer."""
    home = home_country or orders["country"].mode().iloc[0]
    results = [
        welch_test(
            orders.loc[orders["country"] != home, "order_value"],
            orders.loc[orders["country"] == home, "order_value"],
            "international", "domestic",
            f"International orders differ in value from {home} orders",
        ),
        welch_test(
            orders.loc[orders["month"].isin([10, 11, 12]), "order_value"],
            orders.loc[~orders["month"].isin([10, 11, 12]), "order_value"],
            "Q4", "Jan-Sep",
            "Orders in the Oct-Dec peak are worth more than the rest of the year",
        ),
        pearson_test(
            orders["distinct_products"], orders["order_value"],
            "Orders with a wider range of products are worth more",
        ),
        pearson_test(
            rfm["frequency"], rfm["monetary"] / rfm["frequency"],
            "Customers who order more often spend more per order",
        ),
    ]
    return results
