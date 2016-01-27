# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('websites', '0003_website_developer_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='website',
            name='tv_featured',
            field=models.PositiveIntegerField(null=True),
            preserve_default=True,
        ),
    ]
