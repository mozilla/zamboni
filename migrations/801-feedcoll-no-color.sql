ALTER TABLE mkt_feed_collection
    DROP COLUMN color,
    ADD COLUMN background_color varchar(7) NULL;
