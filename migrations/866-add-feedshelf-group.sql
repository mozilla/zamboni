ALTER TABLE `mkt_feed_shelf_membership` ADD COLUMN `group` int(11) UNSIGNED NULL UNIQUE;
ALTER TABLE `mkt_feed_shelf_membership` ADD CONSTRAINT `mkt_feed_shelf_membership_group`
    FOREIGN KEY (`group`) REFERENCES `translations` (`id`);
