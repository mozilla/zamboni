-- See: https://bugzilla.mozilla.org/show_bug.cgi?id=1017084
ALTER TABLE addons
  DROP FOREIGN KEY `addons_ibfk_5`, -- summary
  DROP FOREIGN KEY `addons_ibfk_6`, -- developercomments
  DROP FOREIGN KEY `addons_ibfk_7`, -- eula
  DROP FOREIGN KEY `addons_ibfk_11`, -- the_reason
  DROP FOREIGN KEY `addons_ibfk_12`, -- the_future
  DROP FOREIGN KEY `addons_ibfk_13`, -- thankyou_note
  DROP FOREIGN KEY `addons_ibfk_16`; -- backup_version

ALTER TABLE addons
  DROP COLUMN adminreview,
  DROP COLUMN admin_review_type,
  DROP COLUMN annoying,
  DROP COLUMN auto_repackage,
  DROP COLUMN average_daily_downloads,
  DROP COLUMN average_daily_users,
  DROP COLUMN backup_version,
  DROP COLUMN dev_agreement,
  DROP COLUMN developercomments,
  DROP COLUMN enable_thankyou,
  DROP COLUMN eula,
  DROP COLUMN externalsoftware,
  DROP COLUMN hotness,
  DROP COLUMN locale_disambiguation,
  DROP COLUMN nominationmessage,
  DROP COLUMN outstanding,
  DROP COLUMN paypal_id,
  DROP COLUMN prerelease,
  DROP COLUMN sharecount,
  DROP COLUMN sitespecific,
  DROP COLUMN suggested_amount,
  DROP COLUMN summary,
  DROP COLUMN target_locale,
  DROP COLUMN thankyou_note,
  DROP COLUMN the_future,
  DROP COLUMN the_reason,
  DROP COLUMN total_contributions,
  DROP COLUMN trusted,
  DROP COLUMN ts_slowness,
  DROP COLUMN viewsource,
  DROP COLUMN wants_contributions;
