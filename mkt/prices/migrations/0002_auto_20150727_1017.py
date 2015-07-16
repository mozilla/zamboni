# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('prices', '0001_initial'),
        ('purchase', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='refund',
            name='contribution',
            field=models.OneToOneField(to='purchase.Contribution'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='refund',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='pricecurrency',
            name='tier',
            field=models.ForeignKey(to='prices.Price'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='pricecurrency',
            unique_together=set([('tier', 'currency', 'carrier', 'region', 'provider')]),
        ),
    ]
