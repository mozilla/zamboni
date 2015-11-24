# -*- coding: utf-8 -*-
import datetime

from django.db import migrations


def add_iarc_waffle(apps, schema_editor):
    # We can't import the Switch model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.create(created=datetime.datetime.now(), name='iarc-upgrade-v2')


class Migration(migrations.Migration):

    dependencies = [
        ('site', '0002_auto_20151109_1326'),
    ]

    operations = [
        migrations.RunPython(add_iarc_waffle)
    ]
