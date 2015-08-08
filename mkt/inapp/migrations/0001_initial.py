# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import mkt.webapps.models
import mkt.translations.models
import mkt.translations.fields


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='InAppProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True, db_index=True)),
                ('guid', models.CharField(max_length=255, unique=True, null=True, blank=True)),
                ('default_locale', models.CharField(default=b'en-us', max_length=10)),
                ('logo_url', models.URLField(max_length=1024, null=True, blank=True)),
                ('simulate', models.CharField(max_length=100, null=True, blank=True)),
                ('stub', models.BooleanField(default=False, db_index=True)),
                ('name', mkt.translations.fields.TranslatedField(related_name='InAppProduct_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=False, unique=True)),
            ],
            options={
                'db_table': 'inapp_products',
            },
            bases=(mkt.webapps.models.UUIDModelMixin, models.Model),
        ),
    ]
