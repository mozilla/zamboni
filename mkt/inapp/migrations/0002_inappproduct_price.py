# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inapp', '0001_initial'),
        ('prices', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='inappproduct',
            name='price',
            field=models.ForeignKey(to='prices.Price'),
            preserve_default=True,
        ),
    ]
