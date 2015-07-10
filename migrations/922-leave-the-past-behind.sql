
-- o/` Leave the past behind, just walk away o/`

DROP TABLE IF EXISTS auth_user_groups;
DROP TABLE IF EXISTS auth_user_user_permissions;
DROP TABLE IF EXISTS django_admin_log;
DROP TABLE IF EXISTS auth_user;
DROP TABLE IF EXISTS addons_categories;
DROP TABLE IF EXISTS categories;


ALTER TABLE files DROP COLUMN is_packaged;
ALTER TABLE addon_payment_account DROP COLUMN set_price;
