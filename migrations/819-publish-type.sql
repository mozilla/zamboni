-- Add new column.
ALTER TABLE addons ADD COLUMN publish_type TINYINT(2) UNSIGNED NOT NULL DEFAULT 0 AFTER make_public;
-- Addons who had make_public as a value wanted publish_type=amo.PUBLISH_PRIVATE.
UPDATE addons SET publish_type=2 WHERE make_public IS NOT NULL;
-- Remove old column.
ALTER TABLE addons DROP COLUMN make_public;
