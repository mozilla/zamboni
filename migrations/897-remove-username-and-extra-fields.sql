-- This migration was too slow to run on prod as is.
-- In addition to this commit we're going to manually run this SQL on
-- stage to test the removal:
-- https://gist.github.com/kumar303/aff8caedf59da3459bdb



-- MySQL chokes on this migration if FK checks are not disabled, even though
-- no FK relies on any of the modified fields :(
-- SET FOREIGN_KEY_CHECKS=0;

-- username does not exist anymore. Unfortunately we want to keep it because we
-- have started to put fxa uids in there. To make things worse we have some
-- duplicate data with different case ("Austin" and "austin" both exist) to
-- clean up to allow us to run the ALTER succesfully.
-- DROP INDEX `username` ON `users`;

-- Allow NULLs as per model, it will be helpful to clean things up since we can
-- just blank anything that does not look a fxa uid and still be able to add
-- back the unique constraint later.
-- ALTER TABLE `users` CHANGE `username` `fxa_uid`  varchar(255) NULL;
-- UPDATE users SET fxa_uid = NULL WHERE LENGTH(fxa_uid) != 32;

-- Add the unique constraint back, with the new column name.
-- CREATE UNIQUE INDEX `fxa_uid` ON users(fxa_uid);

-- We no longer log login attempts, since they fail at FxA level, before our code.
-- ALTER TABLE `users` DROP COLUMN `last_login_attempt`;
-- ALTER TABLE `users` DROP COLUMN `last_login_attempt_ip`;
-- ALTER TABLE `users` DROP COLUMN `failed_login_attempts`;

-- We no longer need the password field, but keep it for now because it's
-- easier. This migration reverts it to its default length.
-- ALTER TABLE `users` MODIFY `password` varchar(128);

-- SET FOREIGN_KEY_CHECKS=1;
