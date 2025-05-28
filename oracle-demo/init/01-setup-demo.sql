-- oracle-demo/init/01-setup-demo.sql
-- Demo Oracle Database Setup - Fixed for Oracle XE Pluggable Database

-- ═══════════════════════════════════════════════════════════
-- CONNECT TO THE PLUGGABLE DATABASE XEPDB1
-- ═══════════════════════════════════════════════════════════
ALTER SESSION SET CONTAINER = XEPDB1;

-- ═══════════════════════════════════════════════════════════
-- CREATE TABLESPACE FOR DEMO DATA IN PLUGGABLE DATABASE
-- ═══════════════════════════════════════════════════════════
CREATE TABLESPACE demo_data
DATAFILE '/opt/oracle/oradata/XE/XEPDB1/demo_data.dbf' 
SIZE 100M AUTOEXTEND ON NEXT 10M MAXSIZE 1G;

-- ═══════════════════════════════════════════════════════════
-- CREATE TABLE-SPECIFIC USERS (mimics production security)
-- ═══════════════════════════════════════════════════════════

-- Users table reader
CREATE USER users_reader IDENTIFIED BY "UsersTable123"
DEFAULT TABLESPACE demo_data
QUOTA UNLIMITED ON demo_data;

GRANT CONNECT, RESOURCE TO users_reader;
GRANT CREATE SESSION TO users_reader;

-- Orders table reader  
CREATE USER orders_reader IDENTIFIED BY "OrdersTable123"
DEFAULT TABLESPACE demo_data
QUOTA UNLIMITED ON demo_data;

GRANT CONNECT, RESOURCE TO orders_reader;
GRANT CREATE SESSION TO orders_reader;

-- Products table reader
CREATE USER products_reader IDENTIFIED BY "ProductsTable123"
DEFAULT TABLESPACE demo_data
QUOTA UNLIMITED ON demo_data;

GRANT CONNECT, RESOURCE TO products_reader;
GRANT CREATE SESSION TO products_reader;

-- Analytics table reader
CREATE USER analytics_reader IDENTIFIED BY "AnalyticsTable123"
DEFAULT TABLESPACE demo_data
QUOTA UNLIMITED ON demo_data;

GRANT CONNECT, RESOURCE TO analytics_reader;
GRANT CREATE SESSION TO analytics_reader;

-- ═══════════════════════════════════════════════════════════
-- CREATE DEMO TABLES WITH SAMPLE DATA
-- ═══════════════════════════════════════════════════════════

-- Users Table (owned by users_reader)
CONNECT users_reader/"UsersTable123"@XEPDB1;

CREATE TABLE users (
    user_id NUMBER PRIMARY KEY,
    username VARCHAR2(50) NOT NULL UNIQUE,
    email VARCHAR2(100),
    first_name VARCHAR2(50),
    last_name VARCHAR2(50),
    created_date DATE DEFAULT SYSDATE,
    status VARCHAR2(20) DEFAULT 'ACTIVE'
);

INSERT INTO users VALUES (1, 'john_doe', 'john@example.com', 'John', 'Doe', SYSDATE-30, 'ACTIVE');
INSERT INTO users VALUES (2, 'jane_smith', 'jane@example.com', 'Jane', 'Smith', SYSDATE-20, 'ACTIVE');
INSERT INTO users VALUES (3, 'bob_wilson', 'bob@example.com', 'Bob', 'Wilson', SYSDATE-10, 'INACTIVE');
COMMIT;

-- Orders Table (owned by orders_reader)
CONNECT orders_reader/"OrdersTable123"@XEPDB1;

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    user_id NUMBER,
    product_id NUMBER,
    quantity NUMBER,
    order_date DATE DEFAULT SYSDATE,
    total_amount NUMBER(10,2),
    status VARCHAR2(20) DEFAULT 'PENDING'
);

INSERT INTO orders VALUES (1001, 1, 501, 2, SYSDATE-5, 99.98, 'COMPLETED');
INSERT INTO orders VALUES (1002, 2, 502, 1, SYSDATE-3, 149.99, 'SHIPPED');
INSERT INTO orders VALUES (1003, 1, 503, 3, SYSDATE-1, 299.97, 'PENDING');
COMMIT;

-- Products Table (owned by products_reader)
CONNECT products_reader/"ProductsTable123"@XEPDB1;

CREATE TABLE products (
    product_id NUMBER PRIMARY KEY,
    product_name VARCHAR2(100),
    category VARCHAR2(50),
    price NUMBER(10,2),
    stock_quantity NUMBER,
    description CLOB
);

INSERT INTO products VALUES (501, 'Laptop Pro 15', 'Electronics', 49.99, 25, 'High-performance laptop');
INSERT INTO products VALUES (502, 'Wireless Mouse', 'Electronics', 149.99, 50, 'Ergonomic wireless mouse');
INSERT INTO products VALUES (503, 'Coffee Maker', 'Appliances', 99.99, 15, 'Automatic drip coffee maker');
COMMIT;

-- Analytics Table (owned by analytics_reader)
CONNECT analytics_reader/"AnalyticsTable123"@XEPDB1;

CREATE TABLE sales_analytics (
    metric_id NUMBER PRIMARY KEY,
    metric_name VARCHAR2(100),
    metric_value NUMBER,
    metric_date DATE,
    category VARCHAR2(50)
);

INSERT INTO sales_analytics VALUES (1, 'Daily Revenue', 1249.95, SYSDATE, 'SALES');
INSERT INTO sales_analytics VALUES (2, 'Active Users', 156, SYSDATE, 'USERS');
INSERT INTO sales_analytics VALUES (3, 'Conversion Rate', 3.45, SYSDATE, 'MARKETING');
COMMIT;

-- ═══════════════════════════════════════════════════════════
-- GRANT CROSS-TABLE ACCESS FOR JOINS (if needed)
-- ═══════════════════════════════════════════════════════════
CONNECT system/"DemoPassword123"@XEPDB1;

-- Allow analytics user to read from other tables for reporting
GRANT SELECT ON users_reader.users TO analytics_reader;
GRANT SELECT ON orders_reader.orders TO analytics_reader;
GRANT SELECT ON products_reader.products TO analytics_reader;

-- Create synonyms for easier access
CONNECT analytics_reader/"AnalyticsTable123"@XEPDB1;
CREATE SYNONYM users FOR users_reader.users;
CREATE SYNONYM orders FOR orders_reader.orders;
CREATE SYNONYM products FOR products_reader.products;