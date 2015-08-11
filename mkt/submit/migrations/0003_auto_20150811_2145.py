# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('submit', '0002_appsubmissionchecklist_addon'),
        ('webapps', '0002_auto_20150811_2145'),
    ]

    operations = [
        migrations.RenameField(
            model_name='appsubmissionchecklist',
            old_name='addon',
            new_name='webapp',
        ),
    ]
