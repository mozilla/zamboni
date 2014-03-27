CREATE TABLE `webapps_form_factors` (
    `id` int(11) AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `addon_id` int(11) NOT NULL,
    `form_factor_id` integer UNSIGNED NOT NULL,
    UNIQUE (`addon_id`, `form_factor_id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;
CREATE INDEX `webapps_form_factors_addon_id` ON `webapps_form_factors` (`addon_id`);
CREATE INDEX `webapps_form_factors_form_factor_id` ON `webapps_form_factors` (`form_factor_id`);
