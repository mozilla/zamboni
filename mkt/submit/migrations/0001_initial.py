# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AppSubmissionChecklist',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('terms', models.BooleanField(default=False)),
                ('manifest', models.BooleanField(default=False)),
                ('details', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'submission_checklist_apps',
            },
            bases=(models.Model,),
        ),
    ]
