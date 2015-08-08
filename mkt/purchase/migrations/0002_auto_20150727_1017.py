# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('prices', '0003_auto_20150727_1017'),
        ('purchase', '0001_initial'),
        ('inapp', '0003_inappproduct_webapp'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribution',
            name='addon',
            field=models.ForeignKey(blank=True, to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='contribution',
            name='inapp_product',
            field=models.ForeignKey(blank=True, to='inapp.InAppProduct', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='contribution',
            name='price_tier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, blank=True, to='prices.Price', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='contribution',
            name='related',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, blank=True, to='purchase.Contribution', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='contribution',
            name='user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
    ]
