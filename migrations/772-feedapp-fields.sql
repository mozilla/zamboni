ALTER TABLE `mkt_feed_app`
    ADD COLUMN `background_color` varchar(7) NULL,
    ADD COLUMN `feedapp_type` varchar(30) NOT NULL DEFAULT '',
    ADD COLUMN `has_image` bool NULL DEFAULT false,
    ADD COLUMN `slug` varchar(30) NOT NULL DEFAULT '';
