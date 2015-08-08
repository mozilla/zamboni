# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AbuseReport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('ip_address', models.CharField(default=b'0.0.0.0', max_length=255)),
                ('message', models.TextField()),
                ('read', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'abuse_reports',
            },
            bases=(models.Model,),
        ),
    ]
