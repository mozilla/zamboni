CREATE TABLE `websites_website_keywords` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `website_id` integer NOT NULL,
    `tag_id` integer NOT NULL,
    UNIQUE (`website_id`, `tag_id`)
)
;
ALTER TABLE `websites_website_keywords` ADD CONSTRAINT `tag_id_refs_id_46aff236` FOREIGN KEY (`tag_id`) REFERENCES `tags` (`id`);
CREATE TABLE `websites_website` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `default_locale` varchar(10) NOT NULL,
    `url` integer UNIQUE,
    `title` integer UNIQUE,
    `short_title` integer UNIQUE,
    `description` integer UNIQUE,
    `categories` longtext NOT NULL,
    `icon_type` varchar(25) NOT NULL,
    `icon_hash` varchar(8) NOT NULL,
    `last_updated` datetime NOT NULL
)
;
ALTER TABLE `websites_website` ADD CONSTRAINT `url_refs_id_7f415bd0` FOREIGN KEY (`url`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_website` ADD CONSTRAINT `title_refs_id_7f415bd0` FOREIGN KEY (`title`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_website` ADD CONSTRAINT `short_title_refs_id_7f415bd0` FOREIGN KEY (`short_title`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_website` ADD CONSTRAINT `description_refs_id_7f415bd0` FOREIGN KEY (`description`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_website_keywords` ADD CONSTRAINT `website_id_refs_id_70a70511` FOREIGN KEY (`website_id`) REFERENCES `websites_website` (`id`);
CREATE INDEX `websites_website_keywords_2f78d6d1` ON `websites_website_keywords` (`website_id`);
CREATE INDEX `websites_website_keywords_5659cca2` ON `websites_website_keywords` (`tag_id`);
CREATE INDEX `websites_website_470d4868` ON `websites_website` (`last_updated`);
