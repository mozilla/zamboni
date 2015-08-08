# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import aesfield.field
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Access',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(unique=True, max_length=255)),
                ('secret', aesfield.field.AESField(max_length=255)),
                ('redirect_uri', models.CharField(max_length=255)),
                ('app_name', models.CharField(max_length=255)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'api_access',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Nonce',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('nonce', models.CharField(max_length=128)),
                ('timestamp', models.IntegerField()),
                ('client_key', models.CharField(max_length=255)),
                ('request_token', models.CharField(max_length=128, null=True)),
                ('access_token', models.CharField(max_length=128, null=True)),
            ],
            options={
                'db_table': 'oauth_nonce',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Token',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('token_type', models.SmallIntegerField(choices=[(0, 'Request'), (1, 'Access')])),
                ('key', models.CharField(max_length=255)),
                ('secret', models.CharField(max_length=255)),
                ('timestamp', models.IntegerField()),
                ('verifier', models.CharField(max_length=255, null=True)),
                ('creds', models.ForeignKey(to='api.Access')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'db_table': 'oauth_token',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='nonce',
            unique_together=set([('nonce', 'timestamp', 'client_key', 'request_token', 'access_token')]),
        ),
    ]
