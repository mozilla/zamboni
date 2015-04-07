ALTER TABLE `websites_website` ADD COLUMN `status` integer UNSIGNED NOT NULL, ADD COLUMN `is_disabled` bool NOT NULL;

CREATE TABLE `websites_popularity` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `website_id` integer NOT NULL,
    `value` double precision NOT NULL,
    `region` integer UNSIGNED NOT NULL,
    UNIQUE (`website_id`, `region`)
);
ALTER TABLE `websites_popularity` ADD CONSTRAINT `website_id_ref_popularity` FOREIGN KEY (`website_id`) REFERENCES `websites_website` (`id`);
CREATE INDEX `websites_popularity_website_id` ON `websites_popularity` (`website_id`);
CREATE INDEX `websites_popularity_region_id` ON `websites_popularity` (`region`);

CREATE TABLE `websites_trending` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `website_id` integer NOT NULL,
    `value` double precision NOT NULL,
    `region` integer UNSIGNED NOT NULL,
    UNIQUE (`website_id`, `region`)
);
ALTER TABLE `websites_trending` ADD CONSTRAINT `website_id_ref_trending` FOREIGN KEY (`website_id`) REFERENCES `websites_website` (`id`);
CREATE INDEX `websites_trending_website_id` ON `websites_trending` (`website_id`);
CREATE INDEX `websites_trending_region_id` ON `websites_trending` (`region`);
