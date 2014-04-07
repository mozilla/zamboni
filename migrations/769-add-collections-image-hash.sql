ALTER TABLE app_collections ADD COLUMN image_hash CHAR(8) default NULL;
UPDATE app_collections SET image_hash = 'deadbeef' WHERE has_image = true;
ALTER TABLE app_collections DROP COLUMN has_image;
