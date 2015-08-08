# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DeployBuildId',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('repo', models.CharField(unique=True, max_length=40)),
                ('build_id', models.CharField(default=b'', max_length=20, blank=True)),
            ],
            options={
                'db_table': 'deploy_build_id',
            },
            bases=(models.Model,),
        ),
    ]
