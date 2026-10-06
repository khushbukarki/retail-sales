-- Normalised (3NF) model of the raw transaction export: 5 related tables.
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS invoice_lines;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS countries;

CREATE TABLE countries (
    country_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    country_id   INTEGER NOT NULL REFERENCES countries(country_id)
);

CREATE TABLE products (
    stock_code   TEXT PRIMARY KEY,
    description  TEXT
);

CREATE TABLE invoices (
    invoice_no   TEXT PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    invoice_date TEXT NOT NULL            -- ISO-8601 timestamp
);

CREATE TABLE invoice_lines (
    line_id      INTEGER PRIMARY KEY,
    invoice_no   TEXT NOT NULL REFERENCES invoices(invoice_no),
    stock_code   TEXT NOT NULL REFERENCES products(stock_code),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   REAL NOT NULL CHECK (unit_price > 0)
);

CREATE INDEX idx_lines_invoice  ON invoice_lines(invoice_no);
CREATE INDEX idx_lines_product  ON invoice_lines(stock_code);
CREATE INDEX idx_invoices_cust  ON invoices(customer_id);
CREATE INDEX idx_invoices_date  ON invoices(invoice_date);
