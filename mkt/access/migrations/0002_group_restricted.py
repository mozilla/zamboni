# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('access', '0001_initial'),
        ('access', '0002_auto_20150825_1715'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='restricted',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.RunSQL(
            "UPDATE `groups` SET `restricted`=true WHERE name='Admins';"
        )
    ]
