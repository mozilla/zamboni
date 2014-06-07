ALTER TABLE `mkt_feed_app`
    DROP COLUMN `pullquote_attribution`;

ALTER TABLE `mkt_feed_app`
    ADD COLUMN `pullquote_attribution` varchar(50) NULL DEFAULT '';
