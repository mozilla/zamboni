# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0006_remove_preview_thumbtype'),
    ]

    operations = [
        migrations.AddField(
            model_name='webapp',
            name='tv_featured',
            field=models.PositiveIntegerField(null=True),
            preserve_default=True,
        ),
    ]
