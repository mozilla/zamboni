# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def remove_preload_waffle(apps, schema_editor):
    # We can't import the Switch model directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Switch = apps.get_model('waffle', 'Switch')
    Switch.objects.filter(name='preload-apps').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('site', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(remove_preload_waffle)
    ]
