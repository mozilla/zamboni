-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1008734
DROP TABLE IF EXISTS `features`;
DROP TABLE IF EXISTS `appsupport`;
DROP TABLE IF EXISTS `applications_versions`;
ALTER TABLE categories DROP COLUMN application_id;
ALTER TABLE `file_uploads`
  DROP FOREIGN KEY `compat_with_appver_id_refs_id_3747a309`,
  DROP FOREIGN KEY `compat_with_app_id_refs_id_939661ad`;
ALTER TABLE `file_uploads`
  DROP COLUMN compat_with_app_id,
  DROP COLUMN compat_with_appver_id;
DROP TABLE IF EXISTS `appversions`;
DROP TABLE IF EXISTS `applications`;
