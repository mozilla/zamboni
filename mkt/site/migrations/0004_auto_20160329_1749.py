# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models  # noqa


def remove_iarc_upgrade_waffle(apps, schema_editor):
    # We can't import the Switch model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.filter(name='iarc-upgrade-v2').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('site', '0003_auto_20151123_1219'),
    ]

    operations = [
        migrations.RunPython(remove_iarc_upgrade_waffle)
    ]
