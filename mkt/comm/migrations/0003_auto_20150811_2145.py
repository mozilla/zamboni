# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('webapps', '0002_auto_20150811_2145'),
        ('comm', '0002_auto_20150727_1017'),
    ]

    operations = [
        migrations.RenameField(
            model_name='communicationthread',
            old_name='_addon',
            new_name='_webapp',
        ),
        migrations.AlterField(
            model_name='communicationthread',
            name='_webapp',
            field=models.ForeignKey(related_name='threads', db_column=b'webapp_id', to='webapps.Webapp'),
            preserve_default=True,
        ),

        migrations.AlterUniqueTogether(
            name='communicationthread',
            unique_together=set([('_webapp', '_version')]),
        ),
    ]
