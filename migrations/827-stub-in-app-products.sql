ALTER TABLE inapp_products MODIFY COLUMN webapp_id int(11) unsigned NULL;
ALTER TABLE inapp_products ADD COLUMN simulate varchar(100) NULL;
ALTER TABLE inapp_products ADD COLUMN stub tinyint(2) unsigned DEFAULT 0;
CREATE INDEX inapp_products_stub ON inapp_products (`stub`);
