ALTER TABLE `mkt_feed_item`
    ADD COLUMN `order` smallint,
    ADD COLUMN `item_type` varchar(30) NOT NULL;
