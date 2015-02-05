-- filename is now automatically generated.
ALTER TABLE `langpacks_langpack` DROP COLUMN `filename`;

-- hash was only used for the etag, which is calculated differently now.
ALTER TABLE `langpacks_langpack` DROP COLUMN `hash`;

-- size was only used in the manifest, it's now automatically generated.
ALTER TABLE `langpacks_langpack` DROP COLUMN `size`;

-- original manifest is important to be able to serve a correct minifest.
ALTER TABLE `langpacks_langpack` ADD COLUMN `manifest` longtext NOT NULL;
