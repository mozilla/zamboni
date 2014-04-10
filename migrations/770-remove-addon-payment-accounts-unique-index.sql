ALTER TABLE `addon_payment_account`
    DROP FOREIGN KEY `addon_id_refs_id_e46b699a`,
    DROP INDEX `addon_id`;
ALTER TABLE `addon_payment_account`
    ADD INDEX `addon_id` (`addon_id`),
    ADD CONSTRAINT `addon_id_refs_id_e46b699a` FOREIGN KEY (`addon_id`) REFERENCES `addons` (`id`);
