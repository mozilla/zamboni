# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0016_reset_extensions_translations_locale'),
    ]

    operations = [
        migrations.AlterField(
            model_name='extension',
            name='author',
            field=models.CharField(default=b'', max_length=128, editable=False),
            preserve_default=True,
        ),
    ]
