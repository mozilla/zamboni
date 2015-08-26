# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0001_initial'),
    ]

    operations = [
        # Add the field, without a unique constraint for now. This is splitted
        # into 3 migrations, in order for it to work no matter which state the
        # Extension model is in.
        # See https://docs.djangoproject.com/en/dev/howto/writing-migrations/#migrations-that-add-unique-fields
        migrations.AddField(
            model_name='extension',
            name='uuid',
            field=uuidfield.fields.UUIDField(null=True, max_length=32,
                                             editable=False, blank=True),
        ),
    ]
