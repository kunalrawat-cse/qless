-- add_menu_images.sql - Attach the food photos to an EXISTING database (no data is deleted).
-- Run once:  mysql -u root -p qless_db < sql/add_menu_images.sql
-- (A fresh install does not need this: sql/seed.sql already includes the photos.)

USE qless_db;

UPDATE menu_items SET image_url = '/static/img/menu/idli-sambar.jpg' WHERE name = 'Idli Sambar';
UPDATE menu_items SET image_url = '/static/img/menu/masala-dosa.jpg' WHERE name = 'Masala Dosa';
UPDATE menu_items SET image_url = '/static/img/menu/poha.jpg' WHERE name = 'Poha';
UPDATE menu_items SET image_url = '/static/img/menu/aloo-paratha.jpg' WHERE name = 'Aloo Paratha';
UPDATE menu_items SET image_url = '/static/img/menu/egg-bhurji-pav.jpg' WHERE name = 'Egg Bhurji Pav';
UPDATE menu_items SET image_url = '/static/img/menu/veg-thali.jpg' WHERE name = 'Veg Thali';
UPDATE menu_items SET image_url = '/static/img/menu/chole-bhature.jpg' WHERE name = 'Chole Bhature';
UPDATE menu_items SET image_url = '/static/img/menu/veg-biryani.jpg' WHERE name = 'Veg Biryani';
UPDATE menu_items SET image_url = '/static/img/menu/chicken-biryani.jpg' WHERE name = 'Chicken Biryani';
UPDATE menu_items SET image_url = '/static/img/menu/egg-fried-rice.jpg' WHERE name = 'Egg Fried Rice';
UPDATE menu_items SET image_url = '/static/img/menu/rajma-chawal.jpg' WHERE name = 'Rajma Chawal';
UPDATE menu_items SET image_url = '/static/img/menu/samosa.jpg' WHERE name = 'Samosa';
UPDATE menu_items SET image_url = '/static/img/menu/veg-sandwich.jpg' WHERE name = 'Veg Sandwich';
UPDATE menu_items SET image_url = '/static/img/menu/pav-bhaji.jpg' WHERE name = 'Pav Bhaji';
UPDATE menu_items SET image_url = '/static/img/menu/veg-maggi.jpg' WHERE name = 'Veg Maggi';
UPDATE menu_items SET image_url = '/static/img/menu/fruit-salad.jpg' WHERE name = 'Fruit Salad';
UPDATE menu_items SET image_url = '/static/img/menu/paneer-wrap.jpg' WHERE name = 'Paneer Wrap';
UPDATE menu_items SET image_url = '/static/img/menu/chicken-roll.jpg' WHERE name = 'Chicken Roll';
UPDATE menu_items SET image_url = '/static/img/menu/egg-roll.jpg' WHERE name = 'Egg Roll';
UPDATE menu_items SET image_url = '/static/img/menu/masala-chai.jpg' WHERE name = 'Masala Chai';
UPDATE menu_items SET image_url = '/static/img/menu/cold-coffee.jpg' WHERE name = 'Cold Coffee';
UPDATE menu_items SET image_url = '/static/img/menu/fresh-lime-soda.jpg' WHERE name = 'Fresh Lime Soda';
-- Paneer Rice Bowl: no matching photo was supplied, so image_url stays NULL (category icon is shown).
