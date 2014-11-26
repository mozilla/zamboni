CREATE TABLE `deploy_build_id` (
    `id` int(11) AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `repo` varchar(40) NOT NULL UNIQUE,
    `build_id` varchar(20) NOT NULL
) ENGINE=InnoDB CHARACTER SET utf8 COLLATE utf8_general_ci;
