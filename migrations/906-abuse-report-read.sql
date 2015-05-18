ALTER TABLE `abuse_reports`
    ADD COLUMN `read` bool NOT NULL DEFAULT false,
    ADD COLUMN `website_id` integer;
ALTER TABLE `abuse_reports`
    ADD CONSTRAINT `website_id_ref`
    FOREIGN KEY (`website_id`) REFERENCES `websites_website` (`id`);
-- Mark all existing reports as read.
UPDATE `abuse_reports`
    SET `read`=true;
