# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0018_change_default_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='extension',
            name='icon_hash',
            field=models.CharField(max_length=8, blank=True),
            preserve_default=True,
        ),
    ]
