# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0002_auto_20150727_1017'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='file',
            name='uses_flash',
        ),
    ]
