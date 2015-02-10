-- Remove the old index that had 'created' in it as we made the ordering depend on language only.
DROP INDEX `langpacks_fxos_version_language_active` on `langpacks_langpack`;
CREATE INDEX `langpacks_fxos_version_language_active` ON `langpacks_langpack` (`fxos_version`, `active`, `language`);