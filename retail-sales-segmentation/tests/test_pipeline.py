import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import stats_tests  # noqa: E402
from src.db import connect, load_queries, run_query  # noqa: E402
from src.load_data import clean, generate_synthetic, normalise, write_db  # noqa: E402
from src.rfm import assign_segment, quintile_score, score_rfm  # noqa: E402


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("data") / "test.db"
    df, _ = clean(generate_synthetic(n_customers=300, n_orders=1500, seed=1))
    write_db(normalise(df), path)
    return path


def test_cleaning_removes_bad_rows():
    raw = generate_synthetic(n_customers=100, n_orders=300, seed=2)
    df, log = clean(raw)
    assert log["dropped_cancellations"] > 0 and log["dropped_missing_customer"] > 0
    assert (df["quantity"] > 0).all() and (df["unit_price"] > 0).all()
    assert not df["invoice_no"].str.startswith("C").any()
    assert df["customer_id"].notna().all()


def test_normalised_tables_have_integrity(db):
    con = connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"countries", "customers", "products", "invoices", "invoice_lines"}
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    orphans = con.execute(
        "SELECT COUNT(*) FROM invoice_lines l LEFT JOIN invoices i USING(invoice_no) WHERE i.invoice_no IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    con.close()


def test_every_named_query_runs(db):
    con = connect(db)
    for name in load_queries():
        assert len(run_query(con, name)) > 0, name
    con.close()


def test_revenue_reconciles_between_queries(db):
    con = connect(db)
    total = run_query(con, "kpis")["revenue"].iloc[0]
    assert run_query(con, "rfm_base")["monetary"].sum() == pytest.approx(total, rel=1e-6)
    assert run_query(con, "order_facts")["order_value"].sum() == pytest.approx(total, rel=1e-6)
    con.close()


def test_quintile_score_handles_ties_and_direction():
    s = pd.Series([1, 1, 1, 1, 2, 3, 5, 8, 13, 40])
    scores = quintile_score(s)
    assert scores.between(1, 5).all() and scores.iloc[-1] == 5
    recency = quintile_score(pd.Series(range(1, 11)), higher_is_better=False)
    assert recency.iloc[0] == 5 and recency.iloc[-1] == 1  # most recent customer scores best


def test_segment_rules():
    assert assign_segment(5, 5) == "Champions"
    assert assign_segment(1, 5) == "At risk"
    assert assign_segment(1, 1) == "Hibernating"
    assert assign_segment(5, 1) == "New customers"


def test_rfm_and_stats_on_db(db):
    con = connect(db)
    scored = score_rfm(run_query(con, "rfm_base"))
    orders = run_query(con, "order_facts")
    con.close()
    assert scored["segment"].ne("Other").all()
    results = stats_tests.run_all(orders, scored)
    assert len(results) == 4
    assert all(0 <= r.p_value <= 1 for r in results)


def test_welch_detects_a_real_difference():
    import numpy as np

    rng = np.random.default_rng(0)
    a = pd.Series(rng.lognormal(3.0, 0.5, 500))
    b = pd.Series(rng.lognormal(2.5, 0.5, 500))
    assert stats_tests.welch_test(a, b, "a", "b", "a > b").significant
    same = stats_tests.welch_test(a, a.sample(frac=1, random_state=1), "a", "a", "same")
    assert not same.significant
