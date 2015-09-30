# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0014_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='extension',
            name='author',
            field=models.CharField(default=b'', max_length=255, editable=False),
            preserve_default=True,
        ),
    ]
