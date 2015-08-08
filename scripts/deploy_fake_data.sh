#!/bin/sh
python manage.py migrate --noinput
python manage.py loaddata init
python manage.py generate_apps_from_spec data/apps/test_apps.json
python manage.py generate_feed
python manage.py reindex
