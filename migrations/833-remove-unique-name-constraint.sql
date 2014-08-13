ALTER TABLE inapp_products DROP FOREIGN KEY `inapp_products_name_translation_id`;
ALTER TABLE inapp_products DROP INDEX `name`;
ALTER TABLE inapp_products ADD CONSTRAINT `inapp_products_name_translation_id` FOREIGN KEY (`name`) REFERENCES translations (`id`);
