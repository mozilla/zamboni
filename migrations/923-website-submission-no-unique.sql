-- Removes unique keys from columns.
-- Foreign key constraints prevent us from dropping the index outright.
-- This creates new non-unique indices, and then drops the old unique ones
ALTER TABLE `websites_websitesubmission` DROP INDEX works_well;

ALTER TABLE `websites_websitesubmission` ADD INDEX (description);
ALTER TABLE `websites_websitesubmission` ADD INDEX (name);
ALTER TABLE `websites_websitesubmission` ADD INDEX (submitter_id);

DROP INDEX description on `websites_websitesubmission`;
DROP INDEX name on `websites_websitesubmission`;
DROP INDEX submitter_id on `websites_websitesubmission`;
