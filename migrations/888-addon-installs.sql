CREATE TABLE `addons_installs` (
    `id` int(11) UNSIGNED AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `addon_id` int(11) UNSIGNED NOT NULL,
    `value` double precision NOT NULL,
    `region` int(11) UNSIGNED NOT NULL,
    UNIQUE (`addon_id`, `region`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `addons_installs` ADD CONSTRAINT `addons_installs_addon_id_key` FOREIGN KEY (`addon_id`) REFERENCES `addons` (`id`);

CREATE INDEX `addons_installs_addon_id_index` ON `addons_installs` (`addon_id`);
CREATE INDEX `addons_installs_region_index` ON `addons_installs` (`region`);
