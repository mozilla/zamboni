# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.users.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('developers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('versions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='versionlog',
            name='version',
            field=models.ForeignKey(to='versions.Version'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='userlog',
            name='activity_log',
            field=models.ForeignKey(to='developers.ActivityLog'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='userlog',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='userinappkey',
            name='solitude_seller',
            field=models.ForeignKey(to='developers.SolitudeSeller'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='solitudeseller',
            name='user',
            field=mkt.users.models.UserForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
    ]
