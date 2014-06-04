ALTER TABLE stats_contributions
    ADD COLUMN `inapp_product_id` int(11) UNSIGNED NULL,
    ADD CONSTRAINT `inapp_products_ref` FOREIGN KEY (`inapp_product_id`)
    REFERENCES `inapp_products` (`id`);
