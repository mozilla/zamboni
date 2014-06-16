CREATE TABLE `mkt_feed_shelf_membership` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `app_id` int(11) UNSIGNED NOT NULL,
    `order` smallint,
    `obj_id` int(11) UNSIGNED NOT NULL,
    UNIQUE (`obj_id`, `app_id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `mkt_feed_shelf_membership` ADD CONSTRAINT `mkt_feed_shelf_membership_app_id`
    FOREIGN KEY (`app_id`) REFERENCES `addons` (`id`);

CREATE TABLE `mkt_feed_shelf` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `slug` varchar(30) NOT NULL UNIQUE,
    `image_hash` CHAR(8) default NULL,
    `background_color` CHAR(7) NOT NULL,
    `carrier` int(11) UNSIGNED NULL,
    `description` int(11) UNSIGNED NULL UNIQUE,
    `name` int(11) UNSIGNED NOT NULL UNIQUE,
    `region` int(11) UNSIGNED NULL
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `mkt_feed_shelf` ADD CONSTRAINT `mkt_feed_shelf_description`
    FOREIGN KEY (`description`) REFERENCES `translations` (`id`);
ALTER TABLE `mkt_feed_shelf` ADD CONSTRAINT `mkt_feed_shelf_name`
    FOREIGN KEY (`name`) REFERENCES `translations` (`id`);

ALTER TABLE `mkt_feed_shelf_membership` ADD CONSTRAINT `mkt_feed_shelf_membership_obj_id`
    FOREIGN KEY (`obj_id`) REFERENCES `mkt_feed_shelf` (`id`);

ALTER TABLE `mkt_feed_item` ADD `shelf_id` int(11) UNSIGNED NULL;
ALTER TABLE `mkt_feed_item` ADD CONSTRAINT `mkt_feed_item_shelf_id`
    FOREIGN KEY (`shelf_id`) REFERENCES `mkt_feed_shelf` (`id`);
