-- We use log_activity_app for apps.
-- What's left in here is for themes which we don't need anymore.
DELETE FROM log_activity_user where activity_log_id in (SELECT activity_log_id FROM log_activity_addon);
DELETE FROM log_activity WHERE id IN (SELECT activity_log_id FROM log_activity_addon);
DROP TABLE IF EXISTS log_activity_addon;
