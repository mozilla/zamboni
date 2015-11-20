# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.constants.applications


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0003_appfeatures_has_udpsocket'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='geodata',
            name='banner_message',
        ),
        migrations.RemoveField(
            model_name='geodata',
            name='banner_regions',
        ),
        migrations.AlterField(
            model_name='addondevicetype',
            name='device_type',
            field=models.PositiveIntegerField(default=1, choices=[(1, mkt.constants.applications.DEVICE_DESKTOP), (2, mkt.constants.applications.DEVICE_MOBILE), (3, mkt.constants.applications.DEVICE_TABLET), (4, mkt.constants.applications.DEVICE_GAIA), (5, mkt.constants.applications.DEVICE_TV)]),
            preserve_default=True,
        ),
    ]
