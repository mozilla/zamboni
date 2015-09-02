# -*- coding: utf-8 -*-
from django.db import migrations

from mkt.constants import regions
from mkt.developers.cron import exclude_new_region


def exclude_romania(apps, schema_editor):
    exclude_new_region([regions.ROU])


class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(exclude_romania),
    ]
