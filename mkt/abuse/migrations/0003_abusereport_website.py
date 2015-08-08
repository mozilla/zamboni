# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('abuse', '0002_auto_20150727_1017'),
        ('websites', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='abusereport',
            name='website',
            field=models.ForeignKey(related_name='abuse_reports', to='websites.Website', null=True),
            preserve_default=True,
        ),
    ]
