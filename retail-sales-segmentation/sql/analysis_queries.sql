-- name: kpis
SELECT
    COUNT(DISTINCT i.invoice_no)                      AS orders,
    COUNT(DISTINCT i.customer_id)                     AS customers,
    COUNT(*)                                          AS line_items,
    ROUND(SUM(l.quantity * l.unit_price), 2)          AS revenue,
    ROUND(SUM(l.quantity * l.unit_price) / COUNT(DISTINCT i.invoice_no), 2) AS avg_order_value
FROM invoice_lines l
JOIN invoices i USING (invoice_no);

-- name: monthly_revenue
SELECT
    strftime('%Y-%m', i.invoice_date)                 AS month,
    COUNT(DISTINCT i.invoice_no)                      AS orders,
    ROUND(SUM(l.quantity * l.unit_price), 2)          AS revenue
FROM invoice_lines l
JOIN invoices i USING (invoice_no)
GROUP BY month
ORDER BY month;

-- name: revenue_by_country
SELECT
    c.name                                            AS country,
    COUNT(DISTINCT i.customer_id)                     AS customers,
    ROUND(SUM(l.quantity * l.unit_price), 2)          AS revenue
FROM invoice_lines l
JOIN invoices i   USING (invoice_no)
JOIN customers cu USING (customer_id)
JOIN countries c  USING (country_id)
GROUP BY c.name
ORDER BY revenue DESC
LIMIT 10;

-- name: top_products
SELECT
    p.stock_code,
    p.description,
    SUM(l.quantity)                                   AS units,
    ROUND(SUM(l.quantity * l.unit_price), 2)          AS revenue,
    RANK() OVER (ORDER BY SUM(l.quantity * l.unit_price) DESC) AS revenue_rank
FROM invoice_lines l
JOIN products p USING (stock_code)
GROUP BY p.stock_code, p.description
ORDER BY revenue DESC
LIMIT 10;

-- name: repeat_customer_rate
WITH orders_per_customer AS (
    SELECT customer_id, COUNT(*) AS n_orders
    FROM invoices
    GROUP BY customer_id
)
SELECT
    COUNT(*)                                          AS customers,
    SUM(n_orders > 1)                                 AS repeat_customers,
    ROUND(100.0 * SUM(n_orders > 1) / COUNT(*), 1)    AS repeat_rate_pct
FROM orders_per_customer;

-- name: order_facts
-- One row per order: the base table for the statistical tests.
SELECT
    i.invoice_no,
    i.customer_id,
    i.invoice_date,
    c.name                                            AS country,
    CAST(strftime('%m', i.invoice_date) AS INTEGER)   AS month,
    CAST(strftime('%w', i.invoice_date) AS INTEGER)   AS weekday,
    COUNT(DISTINCT l.stock_code)                      AS distinct_products,
    SUM(l.quantity)                                   AS units,
    SUM(l.quantity * l.unit_price)                    AS order_value
FROM invoices i
JOIN invoice_lines l USING (invoice_no)
JOIN customers cu    USING (customer_id)
JOIN countries c     USING (country_id)
GROUP BY i.invoice_no;

-- name: rfm_base
-- Recency / frequency / monetary per customer, measured from the day after the last sale.
WITH snapshot AS (
    SELECT DATE(MAX(invoice_date), '+1 day') AS snap FROM invoices
),
order_values AS (
    SELECT i.invoice_no, i.customer_id, i.invoice_date,
           SUM(l.quantity * l.unit_price) AS order_value
    FROM invoices i JOIN invoice_lines l USING (invoice_no)
    GROUP BY i.invoice_no
)
SELECT
    customer_id,
    CAST(julianday((SELECT snap FROM snapshot)) - julianday(MAX(invoice_date)) AS INTEGER) AS recency_days,
    COUNT(*)                                          AS frequency,
    ROUND(SUM(order_value), 2)                        AS monetary
FROM order_values
GROUP BY customer_id;
