# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inapp', '0002_inappproduct_price'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='inappproduct',
            name='webapp',
            field=models.ForeignKey(blank=True, to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
    ]
