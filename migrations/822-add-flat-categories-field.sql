-- Add categories json field on addons. JSONField is a TextField, so use a longtext.
ALTER TABLE `addons` ADD COLUMN `categories` longtext;

-- Update categories by manually building the json array from the categories slugs.
UPDATE addons SET addons.categories =
    (SELECT CONCAT('["', GROUP_CONCAT(categories.slug SEPARATOR '", "'), '"]')
     FROM addons_categories
     INNER JOIN categories ON (addons_categories.category_id=categories.id)
     WHERE addons_categories.addon_id = addons.id
     GROUP BY addons.id);

-- Add category to mkt_feed_item. There is only one category per feed item, so we simply store a varchar.
ALTER TABLE `mkt_feed_item` ADD COLUMN  `category` varchar(30) DEFAULT NULL;

-- Update category column from the category slug that category_id points to.
UPDATE mkt_feed_item INNER JOIN categories ON (categories.id = mkt_feed_item.category_id)
    SET mkt_feed_item.category=categories.slug;

-- Drop foreign keys etc, add back an index with the new category column.
ALTER TABLE `mkt_feed_item` DROP FOREIGN KEY `feed_item_category_id`;
ALTER TABLE `mkt_feed_item` DROP KEY `mkt_feed_item_category_region_carrier_idx`;
ALTER TABLE `mkt_feed_item` DROP COLUMN `category_id`;
ALTER TABLE `mkt_feed_item` ADD KEY `mkt_feed_item_category_region_carrier_idx` (`category`,`region`,`carrier`);


-- Add category to app_collections. There is only one category per collection, so we simply store a varchar.
ALTER TABLE `app_collections` ADD COLUMN  `category` varchar(30) DEFAULT NULL;

-- Update category column from the category slug that category_id points to.
UPDATE app_collections INNER JOIN categories ON (categories.id = app_collections.category_id)
    SET app_collections.category=categories.slug;

-- Drop keys etc, add back an index with the new category column.
-- Yes, strangely, app_collections_category_id_idx wasn't a foreign key.
ALTER TABLE `app_collections` DROP KEY `app_collections_category_id_idx`;
ALTER TABLE `app_collections` DROP COLUMN `category_id`;
ALTER TABLE `app_collections` ADD KEY `app_collections_category_idx` (`category`);
