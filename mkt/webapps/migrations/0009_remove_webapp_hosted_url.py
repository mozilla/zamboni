# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0008_remove_china_queue'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='webapp',
            name='hosted_url',
        ),
    ]
