# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0002_webapp_hosted_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='appfeatures',
            name='has_udpsocket',
            field=models.BooleanField(default=False, help_text='UDP Sockets'),
            preserve_default=True,
        ),
    ]
