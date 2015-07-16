# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('prices', '0002_auto_20150727_1017'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='addonpurchase',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='addonpurchase',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='addonpurchase',
            unique_together=set([('addon', 'user')]),
        ),
        migrations.AddField(
            model_name='addonpremium',
            name='addon',
            field=models.OneToOneField(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='addonpremium',
            name='price',
            field=models.ForeignKey(blank=True, to='prices.Price', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='addonpaymentdata',
            name='addon',
            field=models.OneToOneField(related_name='payment_data', to='webapps.Webapp'),
            preserve_default=True,
        ),
    ]
