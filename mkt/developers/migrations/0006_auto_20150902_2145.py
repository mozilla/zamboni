# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0002_auto_20150811_2145'),
        ('developers', '0005_auto_20150827_1230'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='AddonPaymentAccount',
            new_name='WebappPaymentAccount'
        ),
        migrations.RenameField(
            model_name='webapppaymentaccount',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='applog',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='preloadtestplan',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.AlterModelTable(
            name='webapppaymentaccount',
            table='webapp_payment_account'
        )
    ]
