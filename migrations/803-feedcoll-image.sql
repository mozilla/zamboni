ALTER TABLE mkt_feed_collection
    ADD COLUMN image_hash CHAR(8) default NULL;

ALTER TABLE mkt_feed_app
    MODIFY COLUMN type varchar(30) NOT NULL DEFAULT '';
