#!/bin/sh
python manage.py syncdb --noinput
python manage.py loaddata init
schematic migrations/ --fake
python manage.py generate_apps_from_spec data/apps/test_apps.json
python manage.py reindex
