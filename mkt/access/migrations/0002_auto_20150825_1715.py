# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def add_extension_review_permission(apps, schema_editor):
    Group = apps.get_model("access", "Group")
    Group.objects.create(name='FxOS Add-ons Reviewers',
                         rules='Extensions:Review')


class Migration(migrations.Migration):

    dependencies = [
        ('access', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            add_extension_review_permission,
        ),
    ]
