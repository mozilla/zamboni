# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0012_extension_popularity_and_trending'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='extension',
            options={'ordering': ('id',)},
        ),
        migrations.AddField(
            model_name='extension',
            name='disabled',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='last_updated',
            field=models.DateTimeField(db_index=True, null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extension',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')]),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='extension',
            index_together=set([('disabled', 'status')]),
        ),
    ]
