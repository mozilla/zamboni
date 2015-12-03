# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0004_auto_20151120_0650'),
    ]

    operations = [
        migrations.CreateModel(
            name='IARCCert',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('cert_id', uuidfield.fields.UUIDField(unique=True, max_length=32, editable=False, blank=True)),
                ('app', models.OneToOneField(related_name='iarc_cert', to='webapps.Webapp')),
            ],
            options={
                'db_table': 'webapps_iarc_cert',
            },
            bases=(models.Model,),
        ),
    ]
