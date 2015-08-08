# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ProductIcon',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('ext_url', models.CharField(unique=True, max_length=255, db_index=True)),
                ('ext_size', models.IntegerField(db_index=True)),
                ('size', models.IntegerField(db_index=True)),
                ('format', models.CharField(max_length=4)),
            ],
            options={
                'db_table': 'payment_assets',
            },
            bases=(models.Model,),
        ),
    ]
