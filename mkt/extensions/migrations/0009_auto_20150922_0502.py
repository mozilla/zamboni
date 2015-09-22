# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0008_auto_20150918_1103'),
    ]

    operations = [
        migrations.AlterField(
            model_name='extension',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, db_index=True, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')]),
            preserve_default=True,
        ),
    ]
