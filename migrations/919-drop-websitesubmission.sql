ALTER TABLE `websites_websitesubmission_keywords` DROP FOREIGN KEY `websites_websitesubmission_keywords_tag_id`;
ALTER TABLE `websites_websitesubmission_keywords` DROP FOREIGN KEY `websites_websitesubmission_websitesubmission_id`;
DROP TABLE IF EXISTS `websites_websitesubmission_keywords`;

ALTER TABLE `websites_websitesubmission` DROP FOREIGN KEY `websites_websitesubmission_submitter_id`;
ALTER TABLE `websites_websitesubmission` DROP FOREIGN KEY `websites_websitesubmission_name`;
ALTER TABLE `websites_websitesubmission` DROP FOREIGN KEY `websites_websitesubmission_description`;
DROP TABLE IF EXISTS `websites_websitesubmission`;
