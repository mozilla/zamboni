ALTER TABLE `webapps_rating_descriptors`
    ADD COLUMN `has_usk_alcohol` bool NOT NULL,
    ADD COLUMN `has_usk_abstract_violence` bool NOT NULL,
    ADD COLUMN `has_usk_sex_violence_ref` bool NOT NULL,
    ADD COLUMN `has_usk_drug_use` bool NOT NULL,
    ADD COLUMN `has_usk_explicit_violence` bool NOT NULL,
    ADD COLUMN `has_usk_some_swearing` bool NOT NULL,
    ADD COLUMN `has_usk_horror` bool NOT NULL,
    ADD COLUMN `has_usk_nudity` bool NOT NULL,
    ADD COLUMN `has_usk_some_scares` bool NOT NULL,
    ADD COLUMN `has_usk_sex_violence` bool NOT NULL,
    ADD COLUMN `has_usk_sex_ref` bool NOT NULL,
    ADD COLUMN `has_usk_tobacco` bool NOT NULL;
