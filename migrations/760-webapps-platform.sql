CREATE TABLE `webapps_platforms` (
    `id` int(11) AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `addon_id` int(11) NOT NULL,
    `platform_id` integer UNSIGNED NOT NULL,
    UNIQUE (`addon_id`, `platform_id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;
CREATE INDEX `webapps_platforms_addon_id` ON `webapps_platforms` (`addon_id`);
CREATE INDEX `webapps_platforms_platform_id` ON `webapps_platforms` (`platform_id`);
