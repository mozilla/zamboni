# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0010_extension_last_updated'),
    ]

    operations = [
        migrations.AddField(
            model_name='extensionversion',
            name='reviewed',
            field=models.DateTimeField(null=True),
            preserve_default=True,
        ),
    ]
