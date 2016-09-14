# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0014_auto_20160329_1745'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='iarcinfo',
            name='addon',
        ),
        migrations.DeleteModel(
            name='IARCInfo',
        ),
    ]
