# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.fields
import django.db.models.deletion
from django.conf import settings
import mkt.translations.models
import django_extensions.db.fields.json


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Extension',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('default_language', models.CharField(default=b'en-US', max_length=10)),
                ('manifest', django_extensions.db.fields.json.JSONField()),
                ('version', models.CharField(default=b'', max_length=255)),
                ('slug', models.CharField(unique=True, max_length=35)),
                ('status', models.PositiveSmallIntegerField(default=0, db_index=True, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')])),
                ('authors', models.ManyToManyField(to=settings.AUTH_USER_MODEL)),
                ('name', mkt.translations.fields.TranslatedField(related_name='Extension_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', default=None, to_field=b'id', to=mkt.translations.models.Translation, short=True, blank=True, require_locale=True, unique=True)),
            ],
            options={
                'abstract': False,
                'get_latest_by': 'created',
            },
            bases=(models.Model,),
        ),
    ]
