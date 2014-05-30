-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1009930
DROP TABLE IF EXISTS `users_blacklistedusername`;
DROP TABLE IF EXISTS `users_blacklistedemaildomain`;
DROP TABLE IF EXISTS `users_blacklistedpassword`;
DROP TABLE IF EXISTS `users_history`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=996247
-- Warning: This will be slow.
ALTER TABLE `stats_contributions`
  DROP FOREIGN KEY `client_data_id_refs_id_c8ef1728`;
ALTER TABLE `stats_contributions` DROP COLUMN `client_data_id`;
ALTER TABLE `reviews`
  DROP FOREIGN KEY `client_data_id_refs_id_d160c5ba`;
ALTER TABLE `reviews` DROP COLUMN `client_data_id`;
ALTER TABLE `users_install`
  DROP FOREIGN KEY `client_data_id_refs_id_15062d7f`;
ALTER TABLE `users_install` DROP COLUMN `client_data_id`;
DROP TABLE IF EXISTS `client_data`;
