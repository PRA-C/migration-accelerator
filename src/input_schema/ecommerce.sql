CREATE TABLE ecommerce_orders (
    order_id INT NOT NULL,
    customer_id INT NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    customer STRUCT<name VARCHAR(100), email VARCHAR(100), phone VARCHAR(20), loyalty_tier VARCHAR(10)> NOT NULL,
    shipping_address STRUCT<street VARCHAR(255), city VARCHAR(50), state VARCHAR(2), zip_code VARCHAR(10), country VARCHAR(50)> NOT NULL,
    order_items ARRAY<STRUCT<product_id INT, product_name VARCHAR(255), quantity INT, unit_price DECIMAL(10,2)>> NOT NULL,
    payments ARRAY<STRUCT<payment_id VARCHAR(50), method VARCHAR(20), amount DECIMAL(10,2), status VARCHAR(20)>>,
    tags ARRAY<VARCHAR(50)>,
    metadata MAP<STRING, VARCHAR(255)>,
    price_breakdown MAP<STRING, DECIMAL(10,2)>
)