# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('developers', '0005_auto_20150827_1230'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='preloadtestplan',
            name='addon',
        ),
        migrations.DeleteModel(
            name='PreloadTestPlan',
        ),
    ]
