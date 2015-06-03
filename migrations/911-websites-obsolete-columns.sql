-- Websites have no region exclusions and no devices at the moment.
ALTER TABLE `websites_website`
    DROP COLUMN `region_exclusions`;

ALTER TABLE `websites_website`
    DROP COLUMN `devices`;

-- Websites do have the notion of "preferred regions".
ALTER TABLE `websites_website`
    ADD COLUMN `preferred_regions` longtext NOT NULL;
