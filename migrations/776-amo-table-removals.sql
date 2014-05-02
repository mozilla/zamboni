-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999103
DROP TABLE IF EXISTS `piston_token`;
DROP TABLE IF EXISTS `piston_consumer`;
DROP TABLE IF EXISTS `piston_nonce`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999114
DROP TABLE IF EXISTS `blapps`;
DROP TABLE IF EXISTS `blca`;
DROP TABLE IF EXISTS `blplugins`;
DROP TABLE IF EXISTS `blgfxdrivers`;
DROP TABLE IF EXISTS `blitemprefs`;
DROP TABLE IF EXISTS `blitems`;
DROP TABLE IF EXISTS `bldetails`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999142
DROP TABLE IF EXISTS `l10n_eventlog`;
DROP TABLE IF EXISTS `l10n_settings`;
DELETE FROM `groups` WHERE `rules` LIKE '%L10nTools:View%';

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999153
DROP TABLE IF EXISTS `perf_results`;
DROP TABLE IF EXISTS `perf_appversions`;
DROP TABLE IF EXISTS `perf_osversions`;
DELETE FROM `waffle_flag_amo` WHERE `name`='perf-tests';
DELETE FROM `waffle_flag_mkt` WHERE `name`='perf-tests';

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999154
DROP TABLE IF EXISTS `stats_share_counts`;
DROP TABLE IF EXISTS `stats_share_counts_totals`;
DROP TABLE IF EXISTS `stats_collections_share_counts_totals`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999120
DROP TABLE IF EXISTS `compatibility_reports`;
DROP TABLE IF EXISTS `compat_totals`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=999130
DROP TABLE IF EXISTS `discovery_modules`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1001472
DROP TABLE IF EXISTS `stats_addons_collections_counts`;
DROP TABLE IF EXISTS `stats_collections_counts`;
DROP TABLE IF EXISTS `stats_collections`;
DROP TABLE IF EXISTS `download_counts`;
DROP TABLE IF EXISTS `update_counts`;
DROP TABLE IF EXISTS `global_stats`;
DROP TABLE IF EXISTS `theme_user_counts`;

-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1000989
DROP TABLE IF EXISTS `validation_job`;
DROP TABLE IF EXISTS `validation_result`;
