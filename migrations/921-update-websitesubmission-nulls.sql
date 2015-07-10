ALTER TABLE `websites_websitesubmission` MODIFY `date_approved` datetime;
ALTER TABLE `websites_websitesubmission` MODIFY `icon_type` varchar(25);
ALTER TABLE `websites_websitesubmission` MODIFY `icon_hash` varchar(8);

# Remove keywords m2m, replace with a JSON field representing the same thing.
DROP TABLE `websites_websitesubmission_keywords`;
ALTER TABLE `websites_websitesubmission` ADD COLUMN keywords longtext NOT NULL;
