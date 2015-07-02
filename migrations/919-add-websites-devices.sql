-- Add devices column, which is a JSON array of supported device ids.
ALTER TABLE `websites_website` ADD COLUMN `devices` longtext NOT NULL;
-- Start with all existing websites compatible with
-- all mobile (2, 4) / tablet (3), but not desktop (1).
UPDATE `websites_website` SET devices='[2, 3, 4]';
