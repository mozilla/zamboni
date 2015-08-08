# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import uuidfield.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CommAttachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('filepath', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=255, blank=True)),
                ('mimetype', models.CharField(max_length=255, blank=True)),
            ],
            options={
                'ordering': ('id',),
                'db_table': 'comm_attachments',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CommunicationNote',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('read_permission_public', models.BooleanField(default=False)),
                ('read_permission_developer', models.BooleanField(default=True)),
                ('read_permission_reviewer', models.BooleanField(default=True)),
                ('read_permission_senior_reviewer', models.BooleanField(default=True)),
                ('read_permission_mozilla_contact', models.BooleanField(default=True)),
                ('read_permission_staff', models.BooleanField(default=True)),
                ('note_type', models.IntegerField(default=0)),
                ('body', models.TextField(null=True)),
            ],
            options={
                'db_table': 'comm_thread_notes',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CommunicationThread',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('read_permission_public', models.BooleanField(default=False)),
                ('read_permission_developer', models.BooleanField(default=True)),
                ('read_permission_reviewer', models.BooleanField(default=True)),
                ('read_permission_senior_reviewer', models.BooleanField(default=True)),
                ('read_permission_mozilla_contact', models.BooleanField(default=True)),
                ('read_permission_staff', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'comm_threads',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CommunicationThreadCC',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('thread', models.ForeignKey(related_name='thread_cc', to='comm.CommunicationThread')),
                ('user', models.ForeignKey(related_name='comm_thread_cc', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'comm_thread_cc',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CommunicationThreadToken',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('uuid', uuidfield.fields.UUIDField(unique=True, max_length=32, editable=False, blank=True)),
                ('use_count', models.IntegerField(default=0, help_text=b'Stores the number of times the token has been used')),
                ('thread', models.ForeignKey(related_name='token', to='comm.CommunicationThread')),
                ('user', models.ForeignKey(related_name='comm_thread_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'comm_thread_tokens',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='communicationthreadtoken',
            unique_together=set([('thread', 'user')]),
        ),
        migrations.AlterUniqueTogether(
            name='communicationthreadcc',
            unique_together=set([('user', 'thread')]),
        ),
    ]
