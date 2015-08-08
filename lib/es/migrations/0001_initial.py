# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Reindexing',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('alias', models.CharField(max_length=255)),
                ('old_index', models.CharField(max_length=255, null=True)),
                ('new_index', models.CharField(max_length=255)),
            ],
            options={
                'db_table': 'zadmin_reindexing',
            },
            bases=(models.Model,),
        ),
    ]
