# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0017_author_field_length'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='extension',
            options={'ordering': ('-id',)},
        ),
    ]
