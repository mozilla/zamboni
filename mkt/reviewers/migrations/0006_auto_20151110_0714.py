# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reviewers', '0005_merge'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='additionalreview',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='additionalreview',
            name='app',
        ),
        migrations.RemoveField(
            model_name='additionalreview',
            name='reviewer',
        ),
        migrations.DeleteModel(
            name='AdditionalReview',
        ),
    ]
