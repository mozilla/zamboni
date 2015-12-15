# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import mkt.translations.models
import mkt.translations.fields


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        ('websites', '0002_website_tv_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='website',
            name='developer_name',
            field=mkt.translations.fields.TranslatedField(related_name='Website_developer_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'developer_name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
    ]
