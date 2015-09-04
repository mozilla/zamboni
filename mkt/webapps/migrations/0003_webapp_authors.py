# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webapps', '0002_auto_20150811_2145'),
    ]

    operations = [
        migrations.AddField(
            model_name='webapp',
            name='authors',
            field=models.ManyToManyField(related_name='webapps', through='webapps.WebappUser', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
    ]
