-- In case any were added in previous migrations.
DELETE FROM `webapps_platforms`;
DELETE FROM `webapps_form_factors`;

-- Copy DESKTOP to DESKTOP.
INSERT INTO `webapps_platforms` (`addon_id`, `platform_id`, `created`, `modified`)
  SELECT `addon_id`, 1, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type`=1;
-- Copy ANDROID_MOBILE and ANDROID_TABLET to ANDROID.
INSERT INTO `webapps_platforms` (`addon_id`, `platform_id`, `created`, `modified`)
  SELECT `addon_id`, 2, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type` IN (2,3) GROUP BY `addon_id`;
-- Copy GAIA to FXOS.
INSERT INTO `webapps_platforms` (`addon_id`, `platform_id`, `created`, `modified`)
  SELECT `addon_id`, 3, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type`=4;

-- Prior Desktop device types are assumed a desktop form factor.
INSERT INTO `webapps_form_factors` (`addon_id`, `form_factor_id`, `created`, `modified`)
  SELECT `addon_id`, 1, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type`=1;
-- Prior Android mobile device types are assumed a mobile form factor.
-- Prior FxOS device types are assumed a mobile form factor.
INSERT INTO `webapps_form_factors` (`addon_id`, `form_factor_id`, `created`, `modified`)
  SELECT `addon_id`, 2, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type` IN (2,4) GROUP BY `addon_id`;
-- Prior Android tablet device types are assumed a tablet form factor.
INSERT INTO `webapps_form_factors` (`addon_id`, `form_factor_id`, `created`, `modified`)
  SELECT `addon_id`, 3, `created`, `modified` FROM `addons_devicetypes` WHERE `device_type`=3;
