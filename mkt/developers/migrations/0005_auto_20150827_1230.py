# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('developers', '0004_auto_20150824_0820'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='activitylogattachment',
            name='activity_log',
        ),
        migrations.DeleteModel(
            name='ActivityLogAttachment',
        ),
    ]
