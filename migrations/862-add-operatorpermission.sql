CREATE TABLE `operator_permission` (
    `id` int(11) unsigned AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `carrier` int(11) UNSIGNED NOT NULL,
    `region` int(11) UNSIGNED NOT NULL,
    `user_id` int(11) UNSIGNED NOT NULL,
    UNIQUE (`user_id`, `carrier`, `region`)
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;

ALTER TABLE `operator_permission` ADD CONSTRAINT `operator_permission_user_id`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);
