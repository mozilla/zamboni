ALTER TABLE waffle_flag_mkt_users
    ALGORITHM=INPLACE,
    CHANGE COLUMN user_id userprofile_id int(11) unsigned NOT NULL;
