-- TERADATA: Regional monthly sales with rolling averages
-- Tables: customers, orders (from input_schema)

SELECT
    TRUNC(o.order_date, 'MM') AS sales_month,
    c.country,
    c.city,
    COUNT(DISTINCT c.customer_id) AS active_customers,
    COUNT(o.order_id) AS order_count,
    SUM(o.amount) AS gross_revenue,
    AVG(o.amount) AS avg_order_amount,
    SUM(o.amount) / NULLIF(COUNT(DISTINCT c.customer_id), 0) AS revenue_per_customer,
    AVG(SUM(o.amount)) OVER (
        PARTITION BY c.country
        ORDER BY TRUNC(o.order_date, 'MM')
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3mo_revenue
FROM customers c
INNER JOIN orders o
    ON c.customer_id = o.customer_id
WHERE o.order_date >= ADD_MONTHS(CURRENT_DATE, -24)
    AND o.status NOT IN ('CANCELLED', 'REFUNDED')
GROUP BY TRUNC(o.order_date, 'MM'), c.country, c.city
HAVING SUM(o.amount) > 500
ORDER BY c.country, sales_month, gross_revenue DESC;
