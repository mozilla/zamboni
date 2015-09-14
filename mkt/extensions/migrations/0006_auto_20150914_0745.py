# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0005_auto_20150902_0755'),
    ]

    operations = [
        migrations.AlterField(
            model_name='extension',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, db_index=True, choices=[(0, 'Incomplete'), (2, 'Pending approval'), (4, 'Published'), (5, 'Obsolete'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved'), (15, 'Blocked'), (16, 'Unlisted')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='extensionversion',
            name='status',
            field=models.PositiveSmallIntegerField(default=0, db_index=True, choices=[(0, 'Incomplete'), (2, 'Pending approval'), (4, 'Published'), (5, 'Obsolete'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved'), (15, 'Blocked'), (16, 'Unlisted')]),
            preserve_default=True,
        ),
    ]
