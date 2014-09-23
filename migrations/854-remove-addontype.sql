-- addons_ibfk_1 should be 'addontype_id', unfortunately we have to drop FKs
-- by constraint name.
ALTER TABLE addons DROP FOREIGN KEY addons_ibfk_1;  
ALTER TABLE addons DROP COLUMN addontype_id;
DROP TABLE addontypes;
