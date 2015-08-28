# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.fields
import django.db.models.deletion
import mkt.translations.models


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0007_extensionversion_size'),
    ]

    operations = [
        migrations.AlterField(
            model_name='extension',
            name='default_language',
            field=models.CharField(default=b'en-US', max_length=10, editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='description',
            field=mkt.translations.fields.TranslatedField(related_name='Extension_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', default=None, to_field=b'id', editable=False, to=mkt.translations.models.Translation, short=True, blank=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='name',
            field=mkt.translations.fields.TranslatedField(related_name='Extension_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', default=None, to_field=b'id', editable=False, to=mkt.translations.models.Translation, short=True, blank=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
    ]
