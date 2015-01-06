/* Note 2 entries in this table on prod. */
RENAME TABLE addons_blacklistedslug TO addons_blocked_slug;
/* Note 63505 entries in this table on prod. */
ALTER TABLE tags CHANGE blacklisted blocked tinyint(1) NOT NULL DEFAULT '0';
