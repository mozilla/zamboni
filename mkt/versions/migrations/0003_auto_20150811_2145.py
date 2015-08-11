# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('versions', '0002_auto_20150727_1017'),
        ('webapps', '0002_auto_20150811_2145'),
    ]

    operations = [
        migrations.RenameField(
            model_name='version',
            old_name='addon',
            new_name='webapp',
        ),
    ]
