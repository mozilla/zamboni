# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('latecustomization', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='latecustomizationitem',
            name='app',
            field=models.ForeignKey(blank=True, to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='latecustomizationitem',
            name='extension',
            field=models.ForeignKey(blank=True, to='extensions.Extension', null=True),
            preserve_default=True,
        ),
    ]
