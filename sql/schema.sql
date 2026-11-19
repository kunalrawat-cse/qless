-- schema.sql - Creates the Qless database and every table.
-- WARNING: running this file again DELETES all existing Qless data.

CREATE DATABASE IF NOT EXISTS qless_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE qless_db;

-- Drop old tables (children first) so the script can be re-run safely
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS waste_logs;
DROP TABLE IF EXISTS daily_batches;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS pickup_slots;
DROP TABLE IF EXISTS menu_items;
DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;


-- ---------------------------------------------------------
-- USERS: students, kitchen/counter staff and canteen managers
-- ---------------------------------------------------------
CREATE TABLE users (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    full_name           VARCHAR(100) NOT NULL,
    email               VARCHAR(120) NOT NULL UNIQUE,
    campus_id           VARCHAR(30) UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    role                ENUM('student', 'staff', 'manager') NOT NULL DEFAULT 'student',
    dietary_preference  ENUM('any', 'veg', 'non_veg', 'egg') NOT NULL DEFAULT 'any',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ---------------------------------------------------------
-- PASSWORD_RESETS: one-time codes for the "forgot password" flow
-- ---------------------------------------------------------
CREATE TABLE password_resets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    otp_code    CHAR(6) NOT NULL,
    expires_at  DATETIME NOT NULL,
    is_used     TINYINT(1) NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);


-- ---------------------------------------------------------
-- MENU_ITEMS: every dish the canteen sells
-- prepared_batch_qty = how many the kitchen cooked TODAY
-- stock_qty          = how many are still available right now
-- ---------------------------------------------------------
CREATE TABLE menu_items (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(100) NOT NULL,
    description         VARCHAR(255) NOT NULL,
    category            VARCHAR(40) NOT NULL,
    price               DECIMAL(8, 2) NOT NULL,
    food_type           ENUM('veg', 'non_veg', 'egg') NOT NULL,
    allergens           VARCHAR(120) NOT NULL DEFAULT '',
    prep_time_minutes   INT NOT NULL DEFAULT 10,
    image_url           VARCHAR(255),
    prepared_batch_qty  INT NOT NULL DEFAULT 0,
    stock_qty           INT NOT NULL DEFAULT 0,
    is_sold_out         TINYINT(1) NOT NULL DEFAULT 0,
    is_featured         TINYINT(1) NOT NULL DEFAULT 0,
    is_active           TINYINT(1) NOT NULL DEFAULT 1,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (price >= 0),
    CHECK (stock_qty >= 0),
    CHECK (prepared_batch_qty >= 0)
);


-- ---------------------------------------------------------
-- DAILY_BATCHES: history of "Today's Prepared Batch Qty" per item per day
-- (needed for the Prepared vs. Sold chart)
-- ---------------------------------------------------------
CREATE TABLE daily_batches (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    menu_item_id   INT NOT NULL,
    batch_date     DATE NOT NULL,
    prepared_qty   INT NOT NULL,
    UNIQUE KEY one_batch_per_item_per_day (menu_item_id, batch_date),
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id) ON DELETE CASCADE
);


-- ---------------------------------------------------------
-- PICKUP_SLOTS: the 15-minute pickup windows for each day
-- ---------------------------------------------------------
CREATE TABLE pickup_slots (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    slot_date   DATE NOT NULL,
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL,
    capacity    INT NOT NULL DEFAULT 12,
    UNIQUE KEY one_slot_per_start_time (slot_date, start_time),
    CHECK (capacity > 0)
);


-- ---------------------------------------------------------
-- ORDERS: one row per student order
-- Status flow: confirmed -> preparing -> ready -> collected  (or cancelled)
-- ---------------------------------------------------------
CREATE TABLE orders (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT NOT NULL,
    slot_id          INT NOT NULL,
    status           ENUM('confirmed', 'preparing', 'ready', 'collected', 'cancelled')
                     NOT NULL DEFAULT 'confirmed',
    payment_method   ENUM('mock_upi', 'counter') NOT NULL DEFAULT 'counter',
    payment_status   ENUM('pending', 'paid', 'refunded') NOT NULL DEFAULT 'pending',
    total_amount     DECIMAL(8, 2) NOT NULL,
    pickup_otp       CHAR(4) NOT NULL,
    qr_token         VARCHAR(40) NOT NULL UNIQUE,
    uncollected_flag TINYINT(1) NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    preparing_at     DATETIME,
    ready_at         DATETIME,
    collected_at     DATETIME,
    cancelled_at     DATETIME,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (slot_id) REFERENCES pickup_slots(id),
    INDEX idx_orders_slot_status (slot_id, status),
    INDEX idx_orders_student (student_id),
    INDEX idx_orders_created (created_at)
);


-- ---------------------------------------------------------
-- ORDER_ITEMS: the dishes inside each order
-- unit_price is copied at order time so old orders keep their old price
-- ---------------------------------------------------------
CREATE TABLE order_items (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    order_id      INT NOT NULL,
    menu_item_id  INT NOT NULL,
    quantity      INT NOT NULL,
    unit_price    DECIMAL(8, 2) NOT NULL,
    CHECK (quantity > 0),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id)
);


-- ---------------------------------------------------------
-- WASTE_LOGS: food thrown away, logged by staff at end of shift
-- ---------------------------------------------------------
CREATE TABLE waste_logs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    menu_item_id     INT NOT NULL,
    waste_date       DATE NOT NULL,
    quantity_wasted  INT NOT NULL,
    weight_kg        DECIMAL(6, 2),
    reason           ENUM('overproduction', 'spoilage', 'uncollected') NOT NULL,
    notes            VARCHAR(255),
    logged_by        INT,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (quantity_wasted > 0),
    FOREIGN KEY (menu_item_id) REFERENCES menu_items(id),
    FOREIGN KEY (logged_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_waste_date (waste_date)
);


-- ---------------------------------------------------------
-- FEEDBACK: 1-tap rating after pickup (one per order)
-- ---------------------------------------------------------
CREATE TABLE feedback (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    order_id    INT NOT NULL UNIQUE,
    student_id  INT NOT NULL,
    rating      INT NOT NULL,
    comment     VARCHAR(255),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (rating BETWEEN 1 AND 5),
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id)
);


-- ---------------------------------------------------------
-- NOTIFICATIONS: messages shown in the student bell drawer
-- ---------------------------------------------------------
CREATE TABLE notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    message     VARCHAR(255) NOT NULL,
    type        ENUM('order_ready', 'slot_reminder', 'order_cancelled') NOT NULL,
    is_read     TINYINT(1) NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_notifications_user (user_id, is_read)
);