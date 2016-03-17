# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from mkt.constants.applications import DEVICE_TV


def delete_websites(apps, schema_editor):
    Website = apps.get_model("websites", "Website")
    Website.objects.exclude(devices=[DEVICE_TV.id]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('websites', '0004_website_tv_featured'),
    ]

    operations = [
        migrations.RunPython(delete_websites)
    ]
