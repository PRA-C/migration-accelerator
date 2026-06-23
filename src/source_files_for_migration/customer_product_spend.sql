-- TERADATA: Customer orders matched to product catalog by price tier
-- Tables: customers, orders, products (from input_schema)

WITH order_product_match AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.country,
        o.order_id,
        o.order_date,
        o.amount AS order_amount,
        o.status,
        p.product_id,
        p.product_name,
        p.price AS catalog_price,
        ABS(o.amount - p.price) AS price_delta,
        ROW_NUMBER() OVER (
            PARTITION BY o.order_id
            ORDER BY ABS(o.amount - p.price)
        ) AS price_match_rank
    FROM customers c
    INNER JOIN orders o
        ON c.customer_id = o.customer_id
    INNER JOIN products p
        ON o.amount BETWEEN p.price * 0.85 AND p.price * 1.15
    WHERE o.amount > 0
)
SELECT
    customer_id,
    first_name,
    last_name,
    country,
    order_id,
    order_date,
    order_amount,
    status,
    product_id,
    product_name,
    catalog_price,
    price_delta,
    CASE
        WHEN price_delta <= catalog_price * 0.05 THEN 'EXACT_MATCH'
        WHEN price_delta <= catalog_price * 0.10 THEN 'CLOSE_MATCH'
        ELSE 'TIER_MATCH'
    END AS match_quality
FROM order_product_match
WHERE price_match_rank = 1
ORDER BY country, order_date DESC, order_amount DESC;
