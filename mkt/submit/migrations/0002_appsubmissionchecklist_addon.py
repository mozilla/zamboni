# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('submit', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsubmissionchecklist',
            name='addon',
            field=models.OneToOneField(to='webapps.Webapp'),
            preserve_default=True,
        ),
    ]
