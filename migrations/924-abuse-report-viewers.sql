INSERT INTO groups (name, rules, created, modified, notes) VALUES
('App Abuse Viewers', 'Apps:ReadAbuse', NOW(), NOW(), 'Users who can mark read app abuse reports'),
('Website Abuse Viewers', 'Websites:ReadAbuse', NOW(), NOW(), 'Users who can mark read website abuse reports');

ALTER TABLE `reviewer_scores`
    ADD COLUMN `website_id` integer,
    ADD CONSTRAINT `reviewer_scores_website_id_fk`
    FOREIGN KEY (`website_id`) REFERENCES `websites_website` (`id`)
    ON DELETE SET NULL;
