# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def add_uuid_to_exising_extensions(apps, schema_editor):
    Extension = apps.get_model('extensions', 'Extension')
    extensions = Extension.objects.all()
    for extension in extensions:
        extension.uuid = extension._meta.get_field('uuid')._create_uuid()
        extension.save()


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0002_extension_add_uuid'),
    ]

    operations = [
        # Update the uuid field on each row.
        migrations.RunPython(add_uuid_to_exising_extensions),
    ]
