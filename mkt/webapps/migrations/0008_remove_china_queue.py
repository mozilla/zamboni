# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0007_webapp_tv_featured'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='geodata',
            name='popular_region',
        ),
        migrations.RemoveField(
            model_name='geodata',
            name='region_cn_nominated',
        ),
        migrations.RemoveField(
            model_name='geodata',
            name='region_cn_status',
        ),
    ]
