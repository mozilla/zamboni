# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='MonolithRecord',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('key', models.CharField(max_length=255)),
                ('recorded', models.DateTimeField(db_index=True)),
                ('user_hash', models.CharField(max_length=255, blank=True)),
                ('value', models.TextField()),
            ],
            options={
                'db_table': 'monolith_record',
            },
            bases=(models.Model,),
        ),
    ]
