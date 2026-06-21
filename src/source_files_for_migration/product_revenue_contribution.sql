-- DUCKDB: Product catalog contribution vs order revenue bands
-- Tables: customers, orders, products (from input_schema)

WITH product_tiers AS (
    SELECT
        product_id,
        product_name,
        price,
        CASE
            WHEN price < 50 THEN 'BUDGET'
            WHEN price BETWEEN 50 AND 200 THEN 'MID_RANGE'
            WHEN price BETWEEN 200 AND 500 THEN 'PREMIUM'
            ELSE 'LUXURY'
        END AS price_tier,
        NTILE(4) OVER (ORDER BY price) AS price_quartile
    FROM products
),
order_tiers AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        o.amount,
        o.status,
        c.country,
        c.city,
        CASE
            WHEN o.amount < 50 THEN 'BUDGET'
            WHEN o.amount BETWEEN 50 AND 200 THEN 'MID_RANGE'
            WHEN o.amount BETWEEN 200 AND 500 THEN 'PREMIUM'
            ELSE 'LUXURY'
        END AS order_tier
    FROM orders o
    INNER JOIN customers c
        ON o.customer_id = c.customer_id
    WHERE o.status NOT IN ('CANCELLED', 'REFUNDED')
)
SELECT
    pt.price_tier,
    pt.price_quartile,
    COUNT(DISTINCT pt.product_id) AS products_in_tier,
    COUNT(DISTINCT ot.order_id) AS matching_orders,
    COUNT(DISTINCT ot.customer_id) AS unique_buyers,
    SUM(ot.amount) AS tier_revenue,
    AVG(ot.amount) AS avg_order_in_tier,
    SUM(ot.amount) / NULLIF(SUM(SUM(ot.amount)) OVER (), 0) * 100 AS pct_of_total_revenue
FROM product_tiers pt
LEFT JOIN order_tiers ot
    ON pt.price_tier = ot.order_tier
GROUP BY 1, 2
ORDER BY pt.price_quartile;
