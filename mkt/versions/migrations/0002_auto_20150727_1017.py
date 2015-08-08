# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import mkt.translations.models
import mkt.translations.fields


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        ('versions', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='version',
            name='addon',
            field=models.ForeignKey(related_name='versions', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='version',
            name='releasenotes',
            field=mkt.translations.fields.PurifiedField(related_name='Version_releasenotes_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'releasenotes', to_field=b'id', blank=True, to=mkt.translations.models.PurifiedTranslation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
    ]
