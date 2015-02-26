-- MySQL chokes on this migration if FK checks are not disabled, even though
-- no FK relies on any of the modified fields :(
SET FOREIGN_KEY_CHECKS=0;

-- username does not exist anymore. blank everything that doesn't look like a
-- fxa uid first.
UPDATE users SET username = NULL WHERE LENGTH(username) != 32;
ALTER TABLE `users` CHANGE `username` `fxa_uid`  varchar(255);
-- We no longer log login attempts, since they fail at FxA level, before our code.
ALTER TABLE `users` DROP COLUMN `last_login_attempt`;
ALTER TABLE `users` DROP COLUMN `last_login_attempt_ip`;
ALTER TABLE `users` DROP COLUMN `failed_login_attempts`;
-- We no longer need the password field, but keep it for now because it's
-- easier. This migration reverts it to its default length.
ALTER TABLE `users` MODIFY `password` varchar(128);

SET FOREIGN_KEY_CHECKS=1;
