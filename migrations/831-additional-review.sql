CREATE TABLE `additional_review` (
      `id` int(11) UNSIGNED NOT NULL AUTO_INCREMENT,
      `created` datetime NOT NULL,
      `modified` datetime NOT NULL,
      `app_id` int(11) UNSIGNED NOT NULL,
      `queue` varchar(30) NOT NULL,
      `passed` tinyint(1) DEFAULT NULL,
      `review_completed` datetime DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `additional_review_60fc113e` (`app_id`),
      CONSTRAINT `app_id_refs_id_b6387ff3` FOREIGN KEY (`app_id`) REFERENCES `addons` (`id`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;
