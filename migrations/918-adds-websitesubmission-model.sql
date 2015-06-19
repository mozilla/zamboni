CREATE TABLE `websites_websitesubmission_keywords_tag_id` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `websitesubmission_id` integer NOT NULL,
    `tag_id` integer NOT NULL,
    UNIQUE (`websitesubmission_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

ALTER TABLE `websites_websitesubmission_keywords` ADD CONSTRAINT `websites_websitesubmission_keywords__tag_id` FOREIGN KEY (`tag_id`) REFERENCES `tags` (`id`);

CREATE TABLE `websites_websitesubmission` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `date_approved` datetime NULL,
    `name` integer UNIQUE,
    `description` integer UNIQUE,
    `categories` longtext NOT NULL,
    `detected_icon` varchar(255) NOT NULL,
    `icon_type` varchar(25) NOT NULL,
    `icon_hash` varchar(8) NOT NULL,
    `url` varchar(255) NOT NULL,
    `canonical_url` varchar(255),
    `works_well` integer unsigned UNIQUE,
    `submitter_id` integer UNIQUE,
    `public_credit` bool NOT NULL DEFAULT FALSE,
    `why_relevant` longtext NOT NULL,
    `preferred_regions` longtext NOT NULL,
    `approved` bool NOT NULL DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission__submitter_id` FOREIGN KEY (`submitter_id`) REFERENCES `users` (`id`);
ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission__name` FOREIGN KEY (`name`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission__description` FOREIGN KEY (`description`) REFERENCES `translations` (`id`);

ALTER TABLE `websites_websitesubmission_keywords` ADD CONSTRAINT `websites_websitesubmission__websitesubmission_id` FOREIGN KEY (`websitesubmission_id`) REFERENCES `websites_websitesubmission` (`id`);
