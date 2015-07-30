ALTER TABLE `addons`
    ADD COLUMN `promo_img_hash` char(8) NULL;

ALTER TABLE `websites_website`
    ADD COLUMN `promo_img_hash` char(8) NULL;
