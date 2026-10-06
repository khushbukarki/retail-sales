"""Clean the raw transaction export and load it into the normalised SQLite model.

Works with the UCI "Online Retail II" dataset (xlsx or csv) or any file with the same columns:
Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country.

    python -m src.load_data --input data/online_retail_II.xlsx
    python -m src.load_data --synthetic          # generate demo data instead
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .db import DEFAULT_DB, ROOT, connect

# Accept the column names used by both versions of the UCI dataset
COLUMN_MAP = {
    "invoiceno": "invoice_no", "invoice": "invoice_no",
    "stockcode": "stock_code",
    "description": "description",
    "quantity": "quantity",
    "invoicedate": "invoice_date",
    "unitprice": "unit_price", "price": "unit_price",
    "customerid": "customer_id", "customer id": "customer_id",
    "country": "country",
}
NON_PRODUCT_CODES = {"POST", "D", "M", "C2", "DOT", "BANK CHARGES", "CRUK", "PADS", "AMAZONFEE", "ADJUST", "S", "B"}


def read_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None, dtype={"Invoice": str, "InvoiceNo": str, "StockCode": str})
        df = pd.concat(sheets.values(), ignore_index=True)
    else:
        df = pd.read_csv(path, dtype={"Invoice": str, "InvoiceNo": str, "StockCode": str}, encoding="latin-1")
    df = df.rename(columns=lambda c: COLUMN_MAP.get(c.strip().lower(), c))
    missing = set(COLUMN_MAP.values()) - set(df.columns)
    if missing:
        raise ValueError(f"Input is missing columns: {sorted(missing)}")
    return df[list(dict.fromkeys(COLUMN_MAP.values()))]


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Remove rows that would distort sales analysis; return the clean frame and a cleaning log."""
    log = {"raw_rows": len(df)}
    df = df.copy()
    df["invoice_no"] = df["invoice_no"].astype(str).str.strip()
    df["stock_code"] = df["stock_code"].astype(str).str.strip().str.upper()

    steps = [
        ("missing_customer", df["customer_id"].isna()),
        ("cancellations", df["invoice_no"].str.startswith("C")),
        ("non_positive_qty_or_price", (df["quantity"] <= 0) | (df["unit_price"] <= 0)),
        ("non_product_codes", df["stock_code"].isin(NON_PRODUCT_CODES)),
    ]
    for name, mask in steps:
        mask = mask.reindex(df.index, fill_value=False)
        log[f"dropped_{name}"] = int(mask.sum())
        df = df[~mask]

    before = len(df)
    df = df.drop_duplicates()
    log["dropped_duplicates"] = before - len(df)

    df["customer_id"] = df["customer_id"].astype(int)
    df["quantity"] = df["quantity"].astype(int)
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["description"] = df["description"].astype("string").str.strip()
    log["clean_rows"] = len(df)
    return df.reset_index(drop=True), log


def normalise(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the flat export into the 5 tables of the relational model."""
    countries = pd.DataFrame({"name": sorted(df["country"].unique())})
    countries["country_id"] = np.arange(1, len(countries) + 1)
    country_ids = dict(zip(countries["name"], countries["country_id"]))

    # A few customers appear under more than one country: keep their most frequent one
    cust_country = df.groupby("customer_id")["country"].agg(lambda s: s.mode().iloc[0])
    customers = pd.DataFrame({"customer_id": cust_country.index, "country_id": cust_country.map(country_ids).values})

    # Descriptions vary slightly per stock code: keep the most common wording
    desc = df.dropna(subset=["description"]).groupby("stock_code")["description"].agg(lambda s: s.mode().iloc[0])
    products = pd.DataFrame({"stock_code": sorted(df["stock_code"].unique())})
    products["description"] = products["stock_code"].map(desc)

    invoices = (
        df.groupby("invoice_no")
        .agg(customer_id=("customer_id", "first"), invoice_date=("invoice_date", "min"))
        .reset_index()
    )
    invoices["invoice_date"] = invoices["invoice_date"].dt.strftime("%Y-%m-%d %H:%M:%S")

    lines = df[["invoice_no", "stock_code", "quantity", "unit_price"]].copy()
    return {
        "countries": countries[["country_id", "name"]],
        "customers": customers,
        "products": products,
        "invoices": invoices,
        "invoice_lines": lines,
    }


def write_db(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    con = connect(db_path)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())
    for name in ["countries", "customers", "products", "invoices", "invoice_lines"]:
        tables[name].to_sql(name, con, if_exists="append", index=False)
    con.commit()
    con.close()


def generate_synthetic(n_customers: int = 1500, n_orders: int = 9000, seed: int = 42) -> pd.DataFrame:
    """Realistic-looking demo data (seasonal peak, skewed spend, wholesale-sized international orders).
    Use it to try the pipeline; use the real dataset for any reported results."""
    rng = np.random.default_rng(seed)
    countries = np.array(["United Kingdom", "Germany", "France", "Netherlands", "Australia", "Spain", "Norway"])
    cust_country = rng.choice(countries, n_customers, p=[0.8, 0.05, 0.05, 0.03, 0.03, 0.02, 0.02])
    activity = rng.pareto(1.5, n_customers) + 0.1  # a few very active customers

    n_products = 400
    prices = np.round(rng.lognormal(1.0, 0.7, n_products), 2) + 0.25
    stock_codes = [f"{20000 + i}" for i in range(n_products)]
    popularity = rng.dirichlet(np.full(n_products, 0.4))

    days = pd.date_range("2023-01-01", "2024-12-31", freq="D")
    seasonal = 1 + 0.9 * np.exp(-((days.month.values - 11) ** 2) / 2.0)  # Nov peak
    day_w = seasonal / seasonal.sum()

    rows = []
    customers = rng.choice(n_customers, n_orders, p=activity / activity.sum())
    order_days = rng.choice(len(days), n_orders, p=day_w)
    for k, (c, d) in enumerate(zip(customers, order_days)):
        intl = cust_country[c] != "United Kingdom"
        n_items = rng.integers(3, 25 if intl else 15)
        ts = days[d] + pd.Timedelta(hours=int(rng.integers(8, 18)), minutes=int(rng.integers(0, 60)))
        for p in rng.choice(n_products, n_items, replace=False, p=popularity):
            qty = int(rng.integers(1, 6) * (rng.integers(2, 7) if intl else 1) * rng.choice([1, 1, 1, 2, 6, 12]))
            rows.append((f"{500000 + k}", stock_codes[p], f"PRODUCT {stock_codes[p]}", qty, ts, prices[p],
                         float(12000 + c), cust_country[c]))

    df = pd.DataFrame(rows, columns=["invoice_no", "stock_code", "description", "quantity", "invoice_date",
                                     "unit_price", "customer_id", "country"])
    # sprinkle in the kinds of dirty rows the cleaner must remove
    dirty = df.sample(frac=0.02, random_state=seed).copy()
    dirty["invoice_no"] = "C" + dirty["invoice_no"]
    dirty["quantity"] = -dirty["quantity"]
    nulls = df.sample(frac=0.03, random_state=seed + 1).copy()
    nulls["customer_id"] = np.nan
    return pd.concat([df, dirty, nulls], ignore_index=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="raw xlsx/csv export")
    src.add_argument("--synthetic", action="store_true", help="generate demo data")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()

    raw = generate_synthetic() if args.synthetic else read_raw(args.input)
    df, log = clean(raw)
    tables = normalise(df)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    write_db(tables, args.db)

    print("Cleaning log:")
    for k, v in log.items():
        print(f"  {k:<32}{v:>10,}")
    print("\nLoaded tables:")
    for k, v in tables.items():
        print(f"  {k:<32}{len(v):>10,}")
    print(f"\nDatabase written to {args.db}")


if __name__ == "__main__":
    main()
