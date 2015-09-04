# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('abuse', '0003_abusereport_website'),
    ]

    operations = [
        migrations.RenameField(
            model_name='abusereport',
            old_name='addon',
            new_name='webapp',
        ),
    ]
