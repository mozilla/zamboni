# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('reviewers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewerscore',
            name='addon',
            field=models.ForeignKey(related_name='+', blank=True, to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='reviewerscore',
            name='user',
            field=models.ForeignKey(related_name='_reviewer_scores', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
    ]
