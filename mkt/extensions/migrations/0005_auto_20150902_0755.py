# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
import mkt.translations.models
import mkt.translations.fields
import django_extensions.db.fields.json


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        ('extensions', '0004_extension_uuid_unique_constraint'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExtensionVersion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('default_language', models.CharField(default=b'en-US', max_length=10)),
                ('manifest', django_extensions.db.fields.json.JSONField()),
                ('version', models.CharField(default=b'', max_length=23)),
                ('status', models.PositiveSmallIntegerField(default=0, db_index=True, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')])),
                ('extension', models.ForeignKey(related_name='versions', to='extensions.Extension')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='extensionversion',
            unique_together=set([('extension', 'version')]),
        ),
        migrations.RemoveField(
            model_name='extension',
            name='manifest',
        ),
        migrations.RemoveField(
            model_name='extension',
            name='version',
        ),
        migrations.AddField(
            model_name='extension',
            name='description',
            field=mkt.translations.fields.TranslatedField(related_name='Extension_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', default=None, to_field=b'id', to=mkt.translations.models.Translation, short=True, blank=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.RunSQL(
            # Set all existing extensions to status incomplete, we'll need to
            # attach versions to them to make them valid again.
            "UPDATE `extensions_extension` SET `status`=0;"
        )
    ]
