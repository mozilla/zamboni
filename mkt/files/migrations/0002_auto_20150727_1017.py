# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('versions', '0001_initial'),
        ('files', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='file',
            name='version',
            field=models.ForeignKey(related_name='files', to='versions.Version'),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='file',
            index_together=set([('datestatuschanged', 'version'), ('created', 'version')]),
        ),
    ]
