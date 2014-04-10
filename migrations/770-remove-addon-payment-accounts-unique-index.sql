ALTER TABLE `addon_payment_account` DROP INDEX `addon_id`;
ALTER TABLE `addon_payment_account` ADD INDEX `addon_id` (`addon_id`);
