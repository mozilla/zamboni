# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webapps', '0002_auto_20150811_2145'),
        ('prices', '0003_auto_20150727_1017'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='AddonPremium',
            new_name='WebappPremium',
        ),
        migrations.RenameModel(
            old_name='AddonPaymentData',
            new_name='WebappPaymentData',
        ),
        migrations.RenameField(
            model_name='webapppaymentdata',
            old_name='addon',
            new_name='webapp'
        ),
        migrations.RenameModel(
            old_name='AddonPurchase',
            new_name='WebappPurchase'
        ),
        migrations.RenameField(
            model_name='webapppurchase',
            old_name='addon',
            new_name='webapp'
        ),
        migrations.AlterUniqueTogether(
            name='webapppurchase',
            unique_together=set([('webapp', 'user')]),
        ),
        migrations.RenameField(
            model_name='webapppremium',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.AlterModelTable(
            name='webapppremium',
            table='webapps_premium',
        ),
        migrations.AlterModelTable(
            name='webapppaymentdata',
            table='webapp_payment_data',
        ),
        migrations.AlterModelTable(
            name='webapppurchase',
            table='webapp_purchase',
        ),
    ]
