# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_userprofile_shown_dev_agreement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='last_login',
            field=models.DateTimeField(null=True, verbose_name='last login',
                                       blank=True),
        ),
    ]
