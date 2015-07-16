# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Version',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('approvalnotes', models.TextField(default=b'', null=True)),
                ('version', models.CharField(default=b'0.1', max_length=255)),
                ('nomination', models.DateTimeField(null=True)),
                ('reviewed', models.DateTimeField(null=True)),
                ('has_info_request', models.BooleanField(default=False)),
                ('has_editor_comment', models.BooleanField(default=False)),
                ('deleted', models.BooleanField(default=False)),
                ('supported_locales', models.CharField(max_length=255)),
                ('_developer_name', models.CharField(default=b'', max_length=255, editable=False)),
            ],
            options={
                'ordering': ['-created', '-modified'],
                'abstract': False,
                'db_table': 'versions',
                'get_latest_by': 'created',
            },
            bases=(models.Model,),
        ),
    ]
