# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('abuse', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='abusereport',
            name='addon',
            field=models.ForeignKey(related_name='abuse_reports', to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='abusereport',
            name='reporter',
            field=models.ForeignKey(related_name='abuse_reported', blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='abusereport',
            name='user',
            field=models.ForeignKey(related_name='abuse_reports', to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
    ]
