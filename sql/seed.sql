-- seed.sql - Demo users and the canteen menu.
-- Run this AFTER schema.sql.

USE qless_db;

-- ---------------------------------------------------------
-- DEMO USERS  (every account's password is: Qless@123)
-- ---------------------------------------------------------
INSERT INTO users (full_name, email, campus_id, password_hash, role, dietary_preference) VALUES
('Meera Iyer',    'manager@qless.edu',      'EMP001',  'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'manager', 'any'),
('Ravi Kumar',    'staff@qless.edu',        'EMP002',  'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'staff',   'any'),
('Aarav Sharma',  'aarav@campus.edu',       'STU2101', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'any'),
('Diya Patel',    'diya@campus.edu',        'STU2102', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'veg'),
('Rohan Mehta',   'rohan@campus.edu',       'STU2103', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'non_veg'),
('Ananya Singh',  'ananya@campus.edu',      'STU2104', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'veg'),
('Kabir Khan',    'kabir@campus.edu',       'STU2105', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'any'),
('Isha Reddy',    'isha@campus.edu',        'STU2106', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'egg'),
('Vikram Nair',   'vikram@campus.edu',      'STU2107', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'any'),
('Sneha Das',     'sneha@campus.edu',       'STU2108', 'scrypt:32768:8:1$QKZMFxaUbpSILt5i$50841189713543e942fa4aac6e0ab0bedb276abddfda5d579a25ffba9351206b4531b9199b33cc5333f1045c3ffbe37147a83d61dc0ac2864b252519e1782700', 'student', 'veg');


-- ---------------------------------------------------------
-- MENU ITEMS
-- Columns: name, description, category, price, food_type, allergens,
--          prep_time_minutes, image_url, is_featured, prepared_batch_qty, stock_qty, is_sold_out
-- image_url NULL = the app shows a category icon instead of a photo (Paneer Rice Bowl has no photo yet).
-- is_featured = 1 puts the dish in the "Ready Fast / Fresh Today" strip.
-- ---------------------------------------------------------
INSERT INTO menu_items
    (name, description, category, price, food_type, allergens, prep_time_minutes, image_url, is_featured, prepared_batch_qty, stock_qty, is_sold_out)
VALUES
-- Breakfast
('Idli Sambar',      'Three soft steamed idlis with hot sambar and coconut chutney.',      'Breakfast', 40.00,  'veg',     '',               5, '/static/img/menu/idli-sambar.jpg',  0, 40, 32, 0),
('Masala Dosa',      'Crisp rice crepe filled with spiced potato, served with chutneys.',  'Breakfast', 60.00,  'veg',     '',               10, '/static/img/menu/masala-dosa.jpg', 0, 35, 26, 0),
('Poha',             'Light flattened-rice breakfast with peanuts, onion and lemon.',      'Breakfast', 35.00,  'veg',     'Peanuts',        5, '/static/img/menu/poha.jpg',  1, 40, 30, 0),
('Aloo Paratha',     'Whole-wheat paratha stuffed with potato, served with curd.',         'Breakfast', 50.00,  'veg',     'Gluten,Dairy',   10, '/static/img/menu/aloo-paratha.jpg', 0, 30, 22, 0),
('Egg Bhurji Pav',   'Spicy scrambled eggs served with buttered pav.',                     'Breakfast', 55.00,  'egg',     'Egg,Gluten',     10, '/static/img/menu/egg-bhurji-pav.jpg', 0, 25, 18, 0),

-- Meals
('Veg Thali',        'Dal, two sabzis, rice, roti, salad and a sweet.',                    'Meals',     90.00,  'veg',     'Dairy,Gluten',   10, '/static/img/menu/veg-thali.jpg', 0, 60, 41, 0),
('Paneer Rice Bowl', 'Paneer butter masala over steamed rice with salad.',                 'Meals',     110.00, 'veg',     'Dairy',          12, NULL, 0, 35, 24, 0),
('Chole Bhature',    'Spicy chickpea curry with two fluffy fried bhature.',                'Meals',     70.00,  'veg',     'Gluten',         12, '/static/img/menu/chole-bhature.jpg', 0, 30, 4,  0),
('Veg Biryani',      'Fragrant basmati rice cooked with vegetables, served with raita.',   'Meals',     85.00,  'veg',     'Dairy',          12, '/static/img/menu/veg-biryani.jpg', 0, 40, 28, 0),
('Chicken Biryani',  'Hyderabadi-style chicken biryani with raita.',                       'Meals',     120.00, 'non_veg', '',               15, '/static/img/menu/chicken-biryani.jpg', 0, 40, 3,  0),
('Egg Fried Rice',   'Wok-tossed rice with egg, vegetables and soy sauce.',                'Meals',     75.00,  'egg',     'Egg,Soy',        10, '/static/img/menu/egg-fried-rice.jpg', 0, 30, 20, 0),
('Rajma Chawal',     'Kidney bean curry with steamed rice and pickle.',                    'Meals',     70.00,  'veg',     '',               8, '/static/img/menu/rajma-chawal.jpg',  0, 35, 25, 0),

-- Snacks
('Samosa',           'Two crispy samosas with green chutney.',                             'Snacks',    15.00,  'veg',     'Gluten',         3, '/static/img/menu/samosa.jpg',  1, 80, 64, 0),
('Veg Sandwich',     'Grilled sandwich with vegetables, cheese and mint chutney.',         'Snacks',    40.00,  'veg',     'Gluten,Dairy',   5, '/static/img/menu/veg-sandwich.jpg',  1, 40, 31, 0),
('Pav Bhaji',        'Buttery mashed vegetable curry with toasted pav.',                   'Snacks',    65.00,  'veg',     'Gluten,Dairy',   8, '/static/img/menu/pav-bhaji.jpg',  0, 35, 2,  0),
('Veg Maggi',        'Masala noodles cooked with vegetables.',                             'Snacks',    35.00,  'veg',     'Gluten',         6, '/static/img/menu/veg-maggi.jpg',  0, 40, 33, 0),
('Fruit Salad',      'Seasonal fresh-cut fruit bowl.',                                     'Snacks',    45.00,  'veg',     '',               3, '/static/img/menu/fruit-salad.jpg',  1, 25, 19, 0),

-- Rolls & Wraps
('Paneer Wrap',      'Grilled paneer tikka with onions and mint in a soft wrap.',          'Rolls & Wraps', 70.00, 'veg',     'Gluten,Dairy', 8, '/static/img/menu/paneer-wrap.jpg',  0, 25, 0,  1),
('Chicken Roll',     'Spiced chicken with onions and sauce in a paratha roll.',            'Rolls & Wraps', 80.00, 'non_veg', 'Gluten',       10, '/static/img/menu/chicken-roll.jpg', 0, 30, 21, 0),
('Egg Roll',         'Egg-coated paratha roll with onions and chutney.',                   'Rolls & Wraps', 55.00, 'egg',     'Gluten,Egg',   8, '/static/img/menu/egg-roll.jpg',  0, 30, 23, 0),

-- Beverages
('Masala Chai',      'Hot milk tea with ginger and cardamom.',                             'Beverages', 15.00,  'veg',     'Dairy',          3, '/static/img/menu/masala-chai.jpg',  1, 100, 78, 0),
('Cold Coffee',      'Chilled blended coffee with milk and ice.',                          'Beverages', 50.00,  'veg',     'Dairy',          4, '/static/img/menu/cold-coffee.jpg',  0, 40, 29, 0),
('Fresh Lime Soda',  'Sweet or salted lime soda, served cold.',                            'Beverages', 30.00,  'veg',     '',               3, '/static/img/menu/fresh-lime-soda.jpg',  1, 50, 41, 0);