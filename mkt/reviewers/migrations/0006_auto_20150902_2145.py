# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reviewers', '0005_merge'),
        ('webapps', '0002_auto_20150811_2145'),
    ]

    operations = [
        migrations.RenameField(
            model_name='escalationqueue',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='rereviewqueue',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='reviewerscore',
            old_name='addon',
            new_name='webapp',
        ),
    ]
