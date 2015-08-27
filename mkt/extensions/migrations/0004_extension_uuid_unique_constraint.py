# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0003_populate_extension_uuid'),
    ]

    operations = [
        # Add the unique constraint on uuid field now that we have added an
        # uuid on every existing row.
        migrations.AlterField(
            model_name='extension',
            name='uuid',
            field=uuidfield.fields.UUIDField(unique=True, max_length=32,
                                             editable=False, blank=True),
        ),
    ]
