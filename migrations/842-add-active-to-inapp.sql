ALTER TABLE `inapp_products` ADD COLUMN `active` BOOLEAN DEFAULT TRUE;
ALTER TABLE `inapp_products` ADD INDEX `active` (`active`);
