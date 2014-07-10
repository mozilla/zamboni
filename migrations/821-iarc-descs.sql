ALTER TABLE `webapps_rating_descriptors`
    ADD COLUMN `has_esrb_animated_blood` bool NOT NULL,
    ADD COLUMN `has_esrb_cartoon_violence` bool NOT NULL,
    ADD COLUMN `has_esrb_lyrics` bool NOT NULL,
    ADD COLUMN `has_esrb_mature_humor` bool NOT NULL,
    ADD COLUMN `has_esrb_mild_cartoon_violence` bool NOT NULL,
    ADD COLUMN `has_esrb_mild_lyrics` bool NOT NULL,
    ADD COLUMN `has_esrb_mild_sexual_content` bool NOT NULL,
    ADD COLUMN `has_esrb_mild_sexual_themes` bool NOT NULL,
    ADD COLUMN `has_esrb_mild_suggestive_themes` bool NOT NULL,
    ADD COLUMN `has_esrb_sex_violence` bool NOT NULL,
    ADD COLUMN `has_esrb_strong_lyrics` bool NOT NULL,
    ADD COLUMN `has_pegi_horror` bool NOT NULL;
