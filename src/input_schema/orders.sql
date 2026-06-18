CREATE TABLE orders (
    order_id INT NOT NULL,
    customer_id INT,
    order_date DATE,
    amount DECIMAL(10,2),
    company VARCHAR(100),
    status VARCHAR(20)
)