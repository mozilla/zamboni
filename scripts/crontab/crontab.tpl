# Crons are run in UTC time!

MAILTO=marketplace-devs@mozilla.org
DJANGO_SETTINGS_MODULE='settings_local_mkt'

# Enable python27
LD_LIBRARY_PATH=/opt/rh/python27/root/usr/lib64
PATH=/opt/rh/python27/root/usr/bin

HOME=/tmp

# Once per hour.
20 * * * * %(z_cron)s addon_last_updated
50 * * * * %(z_cron)s cleanup_extracted_file

# Twice per day.
25 17,5 * * * %(z_cron)s hide_disabled_files

# Once per day.
05 8 * * * %(z_cron)s email_daily_ratings --settings=settings_local_mkt
10 8 * * * %(z_cron)s update_monolith_stats `/bin/date -d 'yesterday' +\%%Y-\%%m-\%%d`
15 8 * * * %(z_cron)s process_iarc_changes --settings=settings_local_mkt
30 8 * * * %(z_cron)s dump_user_installs_cron --settings=settings_local_mkt
45 9 * * * %(z_cron)s mkt_gc --settings=settings_local_mkt
45 9 * * * %(z_cron)s clean_old_signed --settings=settings_local_mkt
45 10 * * * %(django)s process_addons --task=update_manifests --settings=settings_local_mkt
00 11 * * * %(z_cron)s update_app_trending --settings=settings_local_mkt
30 11 * * * %(z_cron)s update_app_installs --settings=settings_local_mkt
45 11 * * * %(django)s export_data --settings=settings_local_mkt

MAILTO=root
