# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0005_iarccert'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='preview',
            name='thumbtype',
        ),
    ]
