# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_extensions.db.fields.json


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0013_add_disabled_field_alter_status_and_last_updated'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='extensionversion',
            options={'ordering': ('id',)},
        ),
        migrations.AddField(
            model_name='extension',
            name='deleted',
            field=models.BooleanField(default=False, editable=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='extensionversion',
            name='deleted',
            field=models.BooleanField(default=False, editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='slug',
            field=models.CharField(max_length=35, unique=True, null=True),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='extension',
            index_together=set([('deleted', 'disabled', 'status')]),
        ),
        migrations.AlterIndexTogether(
            name='extensionversion',
            index_together=set([('extension', 'deleted', 'status')]),
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='version',
            field=models.CharField(default=None, max_length=23, null=True, editable=False),
            preserve_default=True,
        ),
        # The changes below are not actual db changes, only adding editable=False to various fields.
        migrations.AlterField(
            model_name='extension',
            name='last_updated',
            field=models.DateTimeField(null=True, editable=False, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, editable=False, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='default_language',
            field=models.CharField(default=b'en-US', max_length=10, editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='extension',
            field=models.ForeignKey(related_name='versions', editable=False, to='extensions.Extension'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='manifest',
            field=django_extensions.db.fields.json.JSONField(editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='reviewed',
            field=models.DateTimeField(null=True, editable=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, editable=False, choices=[(0, 'Incomplete'), (2, 'Pending approval'), (4, 'Published'), (5, 'Obsolete'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved'), (15, 'Blocked'), (16, 'Unlisted')]),
            preserve_default=True,
        ),
    ]
