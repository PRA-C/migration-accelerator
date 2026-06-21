-- DUCKDB: Regional monthly sales with rolling averages
-- Tables: customers, orders (from input_schema)

SELECT
    date_trunc('month', o.order_date) AS sales_month,
    c.country,
    c.city,
    COUNT(DISTINCT c.customer_id) AS active_customers,
    COUNT(o.order_id) AS order_count,
    SUM(o.amount) AS gross_revenue,
    AVG(o.amount) AS avg_order_amount,
    SUM(o.amount) / NULLIF(COUNT(DISTINCT c.customer_id), 0) AS revenue_per_customer,
    AVG(SUM(o.amount)) OVER (
        PARTITION BY c.country
        ORDER BY date_trunc('month', o.order_date)
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3mo_revenue
FROM customers c
INNER JOIN orders o
    ON c.customer_id = o.customer_id
WHERE o.order_date >= current_date - INTERVAL '24 months'
    AND o.status NOT IN ('CANCELLED', 'REFUNDED')
GROUP BY 1, 2, 3
HAVING SUM(o.amount) > 500
ORDER BY c.country, sales_month, gross_revenue DESC;
