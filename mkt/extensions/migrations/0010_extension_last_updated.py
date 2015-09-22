# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0009_auto_20150922_0502'),
    ]

    operations = [
        migrations.AddField(
            model_name='extension',
            name='last_updated',
            field=models.DateTimeField(null=True, db_index=True),
            preserve_default=True,
        ),
    ]
