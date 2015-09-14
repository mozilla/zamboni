# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0006_auto_20150914_0745'),
    ]

    operations = [
        migrations.AddField(
            model_name='extensionversion',
            name='size',
            field=models.PositiveIntegerField(default=0, editable=False),
            preserve_default=True,
        ),
    ]
