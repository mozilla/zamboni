# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='lang',
            field=models.CharField(max_length=10, null=True, editable=False, blank=True),
            preserve_default=True,
        ),
    ]
