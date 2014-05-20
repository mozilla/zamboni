-- To avoid having to get these in the correct order.
SET FOREIGN_KEY_CHECKS = 0;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1003275
DROP TABLE IF EXISTS `rereview_queue_theme`;
DROP TABLE IF EXISTS `theme_locks`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1005303
DROP TABLE IF EXISTS `personas`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1004549
DROP TABLE IF EXISTS `collection_features`;
DROP TABLE IF EXISTS `collection_promos`;
DROP TABLE IF EXISTS `collection_subscriptions`;
DROP TABLE IF EXISTS `collections_users`;
DROP TABLE IF EXISTS `collections_votes`;
DROP TABLE IF EXISTS `synced_collections`;
DROP TABLE IF EXISTS `synced_addons_collections`;
DROP TABLE IF EXISTS `featured_collections`;
DROP TABLE IF EXISTS `monthly_pick`;
DROP TABLE IF EXISTS `addon_recommendations`;
DROP TABLE IF EXISTS `addons_collections`;
DROP TABLE IF EXISTS `collection_recommendations`;
DROP TABLE IF EXISTS `stats_collections_share_counts`;
DROP TABLE IF EXISTS `collections`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1005995
DROP TABLE IF EXISTS `incompatible_versions`;
DROP TABLE IF EXISTS `compat_override_range`;
DROP TABLE IF EXISTS `compat_override`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1006897
DROP TABLE IF EXISTS `frozen_addon`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1006903
DROP TABLE IF EXISTS `blacklisted_guids`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1003277
DROP TABLE IF EXISTS `hubrsskeys`;
DROP TABLE IF EXISTS `blogposts`;
DROP TABLE IF EXISTS `hubpromos`;
DROP TABLE IF EXISTS `hubevents`;
DROP TABLE IF EXISTS `submit_step`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1004788
DROP TABLE IF EXISTS `zadmin_siteevent`;
DROP TABLE IF EXISTS `zadmin_siteevent_mkt`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1009305
DROP TABLE IF EXISTS `users_versioncomments`;
DROP TABLE IF EXISTS `versioncomments`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1006905
DROP TABLE IF EXISTS `addons_dependencies`;

--See: https://bugzilla.mozilla.org/show_bug.cgi?id=1009926
DROP TABLE IF EXISTS `approvals`;

SET FOREIGN_KEY_CHECKS = 1;
