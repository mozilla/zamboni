ALTER TABLE users
  DROP FOREIGN KEY `users_ibfk_1`; -- `bio`

ALTER TABLE users
  DROP COLUMN `averagerating`,
  DROP COLUMN `bio`,
  DROP COLUMN `confirmationcode`,
  DROP COLUMN `display_collections`,
  DROP COLUMN `display_collections_fav`,
  DROP COLUMN `emailhidden`,
  DROP COLUMN `homepage`,
  DROP COLUMN `location`,
  DROP COLUMN `notes`,
  DROP COLUMN `notifycompat`,
  DROP COLUMN `notifyevents`,
  DROP COLUMN `occupation`,
  DROP COLUMN `picture_type`,
  DROP COLUMN `resetcode`,
  DROP COLUMN `resetcode_expires`,
  ADD COLUMN `enable_recommendations` tinyint(1) NOT NULL DEFAULT '1';
