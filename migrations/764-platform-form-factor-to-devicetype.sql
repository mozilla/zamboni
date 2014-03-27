SELECT MAX(addon_id) FROM addons_devicetypes INTO @maxid;

-- Copy DESKTOP to DESKTOP.
INSERT INTO addons_devicetypes (addon_id, device_type, created, modified)
  SELECT addon_id, 1, created, modified FROM webapps_platforms WHERE platform_id=1 AND addon_id > @maxid;

-- Copy ANDROID/MOBILE to ANDROID_MOBILE.
INSERT INTO addons_devicetypes (addon_id, device_type, created, modified)
  SELECT addons.id, 2, p.created, p.modified FROM addons
  LEFT JOIN webapps_platforms AS p ON p.addon_id=addons.id
  LEFT JOIN webapps_form_factors AS f ON f.addon_id=addons.id
  WHERE p.platform_id=2 AND f.form_factor_id=2 AND addons.id > @maxid;

-- Copy ANDROID/TABLET to ANDROID_TABLET.
INSERT INTO addons_devicetypes (addon_id, device_type, created, modified)
  SELECT addons.id, 3, p.created, p.modified FROM addons
  LEFT JOIN webapps_platforms AS p ON p.addon_id=addons.id
  LEFT JOIN webapps_form_factors AS f ON f.addon_id=addons.id
  WHERE p.platform_id=2 AND f.form_factor_id=3 AND addons.id > @maxid;

-- Copy FXOS to GAIA.
INSERT INTO addons_devicetypes (addon_id, device_type, created, modified)
  SELECT addon_id, 4, created, modified FROM webapps_platforms WHERE platform_id=3 AND addon_id > @maxid;

DROP TABLE webapps_platforms;
DROP TABLE webapps_form_factors;
