CREATE TABLE `mkt_feed_brand_membership` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `app_id` int(11) UNSIGNED NOT NULL,
    `order` smallint,
    `obj_id` int(11) UNSIGNED NOT NULL,
    UNIQUE (`obj_id`, `app_id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;


CREATE TABLE `mkt_feed_brand` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `slug` varchar(30) NOT NULL UNIQUE,
    `layout` varchar(30) NOT NULL,
    `type` varchar(30) NOT NULL
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `mkt_feed_brand_membership` ADD CONSTRAINT `mkt_feed_brand_membership_app_id`
    FOREIGN KEY (`app_id`) REFERENCES `addons` (`id`);
ALTER TABLE `mkt_feed_brand_membership` ADD CONSTRAINT `mkt_feed_brand_membership_obj_id`
    FOREIGN KEY (`obj_id`) REFERENCES `mkt_feed_brand` (`id`);

ALTER TABLE `mkt_feed_item` ADD `brand_id` int(11) UNSIGNED NULL;
ALTER TABLE `mkt_feed_item` ADD CONSTRAINT `mkt_feed_item_brand_id`
    FOREIGN KEY (`brand_id`) REFERENCES `mkt_feed_brand` (`id`);

ALTER TABLE `mkt_feed_item` DROP FOREIGN KEY `feed_item_collection_id`;
ALTER TABLE `mkt_feed_item` DROP `collection_id`;
