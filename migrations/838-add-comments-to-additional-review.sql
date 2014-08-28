ALTER TABLE `additional_review`
    ADD COLUMN `comment` varchar(255) DEFAULT NULL,
    ADD COLUMN `reviewer_id` int(11) unsigned DEFAULT NULL,
    ADD KEY `additional_review_reviewer_id` (`reviewer_id`),
    ADD CONSTRAINT `additional_review_reviewer_id_refs_users_id`
        FOREIGN KEY (`reviewer_id`) REFERENCES `users` (`id`),
    ADD INDEX `additional_review_queue_created` (`queue`, `created`);
