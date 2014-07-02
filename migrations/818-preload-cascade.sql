ALTER TABLE `preload_test_plans`
    DROP FOREIGN KEY `preinstall_test_plan_addon_fk`;

ALTER TABLE `preload_test_plans`
    ADD CONSTRAINT `preload_test_plan_addon_fk`
    FOREIGN KEY (`addon_id`) REFERENCES `addons` (`id`)
    ON DELETE CASCADE;
