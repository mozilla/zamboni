# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('developers', '0003_auto_20150727_1017'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commentlog',
            name='comments',
            field=models.TextField(),
            preserve_default=True,
        ),
    ]
