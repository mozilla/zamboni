# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.users.models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('developers', '0002_auto_20150727_1017'),
        ('access', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='preloadtestplan',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='paymentaccount',
            name='solitude_seller',
            field=models.ForeignKey(to='developers.SolitudeSeller'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='paymentaccount',
            name='user',
            field=mkt.users.models.UserForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='paymentaccount',
            unique_together=set([('user', 'uri')]),
        ),
        migrations.AddField(
            model_name='grouplog',
            name='activity_log',
            field=models.ForeignKey(to='developers.ActivityLog'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='grouplog',
            name='group',
            field=models.ForeignKey(to='access.Group'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='commentlog',
            name='activity_log',
            field=models.ForeignKey(to='developers.ActivityLog'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='applog',
            name='activity_log',
            field=models.ForeignKey(to='developers.ActivityLog'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='applog',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp', db_constraint=False),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='addonpaymentaccount',
            name='addon',
            field=models.ForeignKey(related_name='app_payment_accounts', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='addonpaymentaccount',
            name='payment_account',
            field=models.ForeignKey(to='developers.PaymentAccount'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='activitylogattachment',
            name='activity_log',
            field=models.ForeignKey(to='developers.ActivityLog'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='activitylog',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
    ]
