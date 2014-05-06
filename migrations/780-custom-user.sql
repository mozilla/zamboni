ALTER TABLE api_access DROP FOREIGN KEY user_id_api;
ALTER TABLE api_access
    CHANGE COLUMN user_id user_id int(11) unsigned NOT NULL,
    ADD CONSTRAINT user_id_api  FOREIGN KEY (user_id) REFERENCES users (id);

ALTER TABLE oauth_token DROP FOREIGN KEY user_id_refs_id_e213c7fc;
ALTER TABLE oauth_token
       CHANGE COLUMN user_id user_id int(11) unsigned DEFAULT NULL,
       ADD CONSTRAINT user_id_oauth_token FOREIGN KEY (user_id) REFERENCES users (id);

ALTER TABLE users
    ADD COLUMN last_login datetime DEFAULT NULL,
    DROP FOREIGN KEY user_id_refs_id_eb1f4611,
    DROP COLUMN user_id;

UPDATE users SET last_login = NOW();



