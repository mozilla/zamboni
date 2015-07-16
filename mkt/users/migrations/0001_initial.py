# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import mkt.site.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last login')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('fxa_uid', models.CharField(max_length=255, unique=True, null=True, blank=True)),
                ('display_name', models.CharField(default=b'', max_length=255, null=True, blank=True)),
                ('email', models.EmailField(max_length=75, unique=True, null=True)),
                ('deleted', models.BooleanField(default=False)),
                ('read_dev_agreement', models.DateTimeField(null=True, blank=True)),
                ('last_login_ip', models.CharField(default=b'', max_length=45, editable=False)),
                ('source', models.PositiveIntegerField(default=0, editable=False, db_index=True)),
                ('is_verified', models.BooleanField(default=True)),
                ('region', models.CharField(max_length=11, null=True, editable=False, blank=True)),
                ('lang', models.CharField(max_length=5, null=True, editable=False, blank=True)),
                ('enable_recommendations', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'users',
            },
            bases=(mkt.site.models.OnChangeMixin, models.Model),
        ),
        migrations.CreateModel(
            name='UserNotification',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('notification_id', models.IntegerField()),
                ('enabled', models.BooleanField(default=False)),
                ('user', models.ForeignKey(related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'users_notifications',
            },
            bases=(models.Model,),
        ),
    ]
