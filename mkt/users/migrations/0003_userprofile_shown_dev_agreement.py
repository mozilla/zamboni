# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_auto_20150826_0807'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='shown_dev_agreement',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
