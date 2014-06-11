ALTER TABLE `mkt_feed_collection_membership` ADD COLUMN
  `group_id` int(11) UNSIGNED NULL UNIQUE;
ALTER TABLE `mkt_feed_collection_membership` ADD CONSTRAINT `mkt_feed_collection_membership_group_id`
    FOREIGN KEY (`group_id`) REFERENCES `translations` (`id`);
