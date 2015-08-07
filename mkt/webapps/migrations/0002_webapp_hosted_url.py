# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='webapp',
            name='hosted_url',
            field=models.URLField(max_length=255, null=True, blank=True),
            preserve_default=True,
        ),
    ]
