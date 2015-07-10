CREATE TABLE `websites_websitesubmission_keywords` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `websitesubmission_id` integer UNIQUE,
    `tag_id` integer unsigned NOT NULL,
    UNIQUE (`websitesubmission_id`, `tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

ALTER TABLE `websites_websitesubmission_keywords` ADD CONSTRAINT `websites_websitesubmission_keywords_tag_id` FOREIGN KEY (`tag_id`) REFERENCES `tags` (`id`);

CREATE TABLE `websites_websitesubmission` (
    `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
    `created` datetime NOT NULL,
    `modified` datetime NOT NULL,
    `date_approved` datetime NULL,
    `name` integer unsigned UNIQUE,
    `description` integer unsigned UNIQUE,
    `categories` longtext NOT NULL,
    `detected_icon` varchar(255) NOT NULL,
    `icon_type` varchar(25) NOT NULL,
    `icon_hash` varchar(8) NOT NULL,
    `url` varchar(255) NOT NULL,
    `canonical_url` varchar(255),
    `works_well` integer unsigned UNIQUE,
    `submitter_id` integer unsigned UNIQUE,
    `public_credit` bool NOT NULL DEFAULT FALSE,
    `why_relevant` longtext NOT NULL,
    `preferred_regions` longtext NOT NULL,
    `approved` bool NOT NULL DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE INDEX websites_websitesubmission_created_idx ON websites_websitesubmission (created);
CREATE INDEX websites_websitesubmission_modified_idx ON websites_websitesubmission (modified);
CREATE INDEX websites_websitesubmission_approved_idx ON websites_websitesubmission (approved);

ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission_submitter_id` FOREIGN KEY (`submitter_id`) REFERENCES `users` (`id`);
ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission_name` FOREIGN KEY (`name`) REFERENCES `translations` (`id`);
ALTER TABLE `websites_websitesubmission` ADD CONSTRAINT `websites_websitesubmission_description` FOREIGN KEY (`description`) REFERENCES `translations` (`id`);

ALTER TABLE `websites_websitesubmission_keywords` ADD CONSTRAINT `websites_websitesubmission_websitesubmission_id` FOREIGN KEY (`websitesubmission_id`) REFERENCES `websites_websitesubmission` (`id`);
