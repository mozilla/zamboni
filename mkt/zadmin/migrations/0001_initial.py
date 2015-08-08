# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Config',
            fields=[
                ('key', models.CharField(max_length=255, serialize=False, primary_key=True)),
                ('value', models.TextField()),
            ],
            options={
                'db_table': 'config',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EmailPreview',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('topic', models.CharField(max_length=255, db_index=True)),
                ('recipient_list', models.TextField()),
                ('from_email', models.EmailField(max_length=75)),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField()),
            ],
            options={
                'db_table': 'email_preview',
            },
            bases=(models.Model,),
        ),
    ]
