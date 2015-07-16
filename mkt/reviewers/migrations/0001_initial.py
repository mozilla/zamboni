# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AdditionalReview',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('queue', models.CharField(max_length=30)),
                ('passed', models.NullBooleanField()),
                ('review_completed', models.DateTimeField(null=True)),
                ('comment', models.CharField(max_length=255, null=True, blank=True)),
            ],
            options={
                'db_table': 'additional_review',
                'get_latest_by': 'created',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CannedResponse',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('sort_group', models.CharField(max_length=255)),
            ],
            options={
                'db_table': 'cannedresponses',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EditorSubscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'editor_subscriptions',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EscalationQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'escalation_queue',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='RereviewQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'rereview_queue',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ReviewerScore',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('score', models.SmallIntegerField()),
                ('note_key', models.SmallIntegerField(default=0, choices=[(0, 'Manual Reviewer Points'), (70, 'Web App Review'), (71, 'Packaged App Review'), (72, 'Web App Re-review'), (73, 'Updated Packaged App Review'), (74, 'Privileged App Review'), (75, 'Updated Privileged App Review'), (81, 'Moderated App Review'), (82, 'App Review Moderation Reverted'), (90, 'Tarako App Review'), (100, 'App Abuse Report Read'), (101, 'Website Abuse Report Read')])),
                ('note', models.CharField(max_length=255, blank=True)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'reviewer_scores',
            },
            bases=(models.Model,),
        ),
    ]
