ALTER TABLE reviews
    ADD COLUMN lang VARCHAR(5);

CREATE INDEX app_reviews_with_lang
    ON reviews (addon_id, reply_to, lang);
