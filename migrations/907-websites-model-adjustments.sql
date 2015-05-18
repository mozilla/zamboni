-- Drop url, we'll replace it with a non-translated field. We don't care about existing data at this point.
ALTER TABLE `websites_website` DROP FOREIGN KEY `url_refs_id_7f415bd0`;
ALTER TABLE `websites_website` DROP COLUMN `url`;

-- Drop short_title, replace with short_name.
ALTER TABLE `websites_website` DROP FOREIGN KEY `short_title_refs_id_7f415bd0`;
ALTER TABLE `websites_website` DROP COLUMN `short_title`;

-- Add optional mobile_url and new url column.
ALTER TABLE `websites_website` ADD COLUMN `mobile_url` varchar(255);
ALTER TABLE `websites_website` ADD COLUMN `url` varchar(255);

-- Add new name and short_name columns and indexes. Those are translated fields.
ALTER TABLE `websites_website` ADD COLUMN `name` integer unsigned REFERENCES `translations` (`id`);
ALTER TABLE `websites_website` ADD COLUMN `short_name` integer unsigned REFERENCES `translations` (`id`);
CREATE INDEX `websites_website_name` ON `websites_website` (`name`);
CREATE INDEX `websites_website_short_name` ON `websites_website` (`short_name`);
