# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0020_change_filename_scheme'),
        ('abuse', '0003_abusereport_website'),
    ]

    operations = [
        migrations.AddField(
            model_name='abusereport',
            name='extension',
            field=models.ForeignKey(related_name='abuse_reports', to='extensions.Extension', null=True),
            preserve_default=True,
        ),
    ]
