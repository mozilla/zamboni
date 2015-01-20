CREATE TABLE `langpacks_langpack` (
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `uuid` char(32) NOT NULL PRIMARY KEY,
    `language` varchar(10) NOT NULL,
    `fxos_version` varchar(255) NOT NULL,
    `version` varchar(255) NOT NULL,
    `filename` varchar(255) NOT NULL,
    `hash` varchar(255) NOT NULL,
    `size` integer UNSIGNED NOT NULL,
    `active` bool NOT NULL
)
;
CREATE INDEX `langpacks_fxos_version_language_active` ON `langpacks_langpack` (`fxos_version`, `language`, `active`);
