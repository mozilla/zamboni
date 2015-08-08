# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Tag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('tag_text', models.CharField(unique=True, max_length=128)),
                ('blocked', models.BooleanField(default=False)),
                ('restricted', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('tag_text',),
                'db_table': 'tags',
            },
            bases=(models.Model,),
        ),
    ]
