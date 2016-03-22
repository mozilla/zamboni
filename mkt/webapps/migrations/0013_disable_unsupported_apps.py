# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from mkt.constants.applications import DEVICE_GAIA
from mkt.constants.base import ADDON_FREE, STATUS_NULL


def disable_unsupported_apps(apps, schema_editor):
    Webapp = apps.get_model("webapps", "Webapp")
    Webapp.objects.exclude(addondevicetype__device_type=DEVICE_GAIA.id).update(
        status=STATUS_NULL)
    Webapp.objects.exclude(premium_type=ADDON_FREE).update(status=STATUS_NULL)


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0012_new_generic_descriptors')
    ]

    operations = [
        migrations.RunPython(disable_unsupported_apps)
    ]
