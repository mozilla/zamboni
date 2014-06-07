CREATE TABLE `mkt_feed_collection_membership` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `app_id` int(11) UNSIGNED NOT NULL,
    `order` smallint,
    `obj_id` int(11) UNSIGNED NOT NULL,
    UNIQUE (`obj_id`, `app_id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

CREATE TABLE `mkt_feed_collection` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `slug` varchar(30) NOT NULL UNIQUE,
    `type` varchar(30) NOT NULL,
    `color` varchar(7) NOT NULL,
    `name` int(11) UNSIGNED NULL UNIQUE,
    `description` int(11) UNSIGNED NULL UNIQUE
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `mkt_feed_collection` ADD CONSTRAINT `mkt_feed_collection_description`
    FOREIGN KEY (`description`) REFERENCES `translations` (`id`);
ALTER TABLE `mkt_feed_collection_membership` ADD CONSTRAINT `mkt_feed_collection_membership_app_id`
    FOREIGN KEY (`app_id`) REFERENCES `addons` (`id`);
ALTER TABLE `mkt_feed_collection_membership` ADD CONSTRAINT `mkt_feed_collection_membership_obj_id`
    FOREIGN KEY (`obj_id`) REFERENCES `mkt_feed_collection` (`id`);

ALTER TABLE `mkt_feed_item` ADD `collection_id` int(11) UNSIGNED NULL;
ALTER TABLE `mkt_feed_item` ADD CONSTRAINT `mkt_feed_item_collection_id`
    FOREIGN KEY (`collection_id`) REFERENCES `mkt_feed_collection` (`id`);
