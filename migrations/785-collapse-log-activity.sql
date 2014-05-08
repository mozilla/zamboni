-- Drop activity log tables from AMO.
DROP TABLE IF EXISTS log_activity_addon;
DROP TABLE IF EXISTS log_activity_app;
DROP TABLE IF EXISTS log_activity_comment;
DROP TABLE IF EXISTS log_activity_group;
DROP TABLE IF EXISTS log_activity_user;
DROP TABLE IF EXISTS log_activity_version;
DROP TABLE IF EXISTS log_activity;

-- Rename activity log tables from MKT.
ALTER TABLE log_activity_addon_mkt RENAME TO log_activity_addon;
ALTER TABLE log_activity_app_mkt RENAME TO log_activity_app;
ALTER TABLE log_activity_attachment_mkt RENAME TO log_activity_attachment;
ALTER TABLE log_activity_comment_mkt RENAME TO log_activity_comment;
ALTER TABLE log_activity_group_mkt RENAME TO log_activity_group;
ALTER TABLE log_activity_user_mkt RENAME TO log_activity_user;
ALTER TABLE log_activity_version_mkt RENAME TO log_activity_version;
ALTER TABLE log_activity_mkt RENAME TO log_activity;

-- Remove the log_activity_addon table and associated records in log_activity.
DELETE FROM log_activity WHERE id IN (SELECT activity_log_id FROM log_activity_addon);
DROP TABLE IF EXISTS log_activity_addon;
