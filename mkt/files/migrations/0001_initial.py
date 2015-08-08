# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.site.models
from django.conf import settings
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='File',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('filename', models.CharField(default=b'', max_length=255)),
                ('size', models.PositiveIntegerField(default=0)),
                ('hash', models.CharField(default=b'', max_length=255)),
                ('status', models.PositiveSmallIntegerField(default=2, db_index=True, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')])),
                ('datestatuschanged', models.DateTimeField(auto_now_add=True, null=True)),
                ('reviewed', models.DateTimeField(null=True)),
                ('uses_flash', models.BooleanField(default=False, db_index=True)),
            ],
            options={
                'abstract': False,
                'db_table': 'files',
                'get_latest_by': 'created',
            },
            bases=(mkt.site.models.OnChangeMixin, models.Model),
        ),
        migrations.CreateModel(
            name='FileUpload',
            fields=[
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('uuid', uuidfield.fields.UUIDField(primary_key=True, serialize=False, editable=False, max_length=32, blank=True, unique=True)),
                ('path', models.CharField(default=b'', max_length=255)),
                ('name', models.CharField(default=b'', help_text=b"The user's original filename", max_length=255)),
                ('hash', models.CharField(default=b'', max_length=255)),
                ('valid', models.BooleanField(default=False)),
                ('validation', models.TextField(null=True)),
                ('task_error', models.TextField(null=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'abstract': False,
                'db_table': 'file_uploads',
                'get_latest_by': 'created',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='FileValidation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('valid', models.BooleanField(default=False)),
                ('errors', models.IntegerField(default=0)),
                ('warnings', models.IntegerField(default=0)),
                ('notices', models.IntegerField(default=0)),
                ('validation', models.TextField()),
                ('file', models.OneToOneField(related_name='validation', to='files.File')),
            ],
            options={
                'db_table': 'file_validation',
            },
            bases=(models.Model,),
        ),
    ]
