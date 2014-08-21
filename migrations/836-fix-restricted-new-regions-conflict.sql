-- Update the `enable_new_regions` column to default to True to not conflict
-- with the webapps_geodata.restricted default.
ALTER TABLE addons
MODIFY COLUMN enable_new_regions TINYINT(1) NOT NULL DEFAULT 1;

-- Set enable_new_regions to True when app is unrestricted.
UPDATE addons
JOIN webapps_geodata ON webapps_geodata.addon_id=addons.id
SET addons.enable_new_regions=1
WHERE webapps_geodata.restricted=0;
