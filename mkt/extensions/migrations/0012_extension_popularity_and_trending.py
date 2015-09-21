# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0011_extensionversion_reviewed'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExtensionPopularity',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('value', models.FloatField(default=0.0)),
                ('region', models.PositiveIntegerField(default=0, db_index=True)),
                ('extension', models.ForeignKey(related_name='popularity', to='extensions.Extension')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WebsiteTrending',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('value', models.FloatField(default=0.0)),
                ('region', models.PositiveIntegerField(default=0, db_index=True)),
                ('extension', models.ForeignKey(related_name='trending', to='extensions.Extension')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='websitetrending',
            unique_together=set([('extension', 'region')]),
        ),
        migrations.AlterUniqueTogether(
            name='extensionpopularity',
            unique_together=set([('extension', 'region')]),
        ),
    ]
