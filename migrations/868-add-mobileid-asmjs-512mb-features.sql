ALTER TABLE `addons_features`
    ADD COLUMN `mobileid` bool NOT NULL;
ALTER TABLE `addons_features`
    ADD COLUMN `precompile_asmjs` bool NOT NULL;
ALTER TABLE `addons_features`
    ADD COLUMN `hardware_512mb_ram` bool NOT NULL;
