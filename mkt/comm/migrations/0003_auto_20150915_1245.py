# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0006_auto_20150914_0745'),
        ('comm', '0002_auto_20150727_1017'),
    ]

    operations = [
        migrations.AddField(
            model_name='communicationthread',
            name='_extension',
            field=models.ForeignKey(related_name='threads', db_column=b'_extension_id', to='extensions.Extension', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='communicationthread',
            name='_extension_version',
            field=models.ForeignKey(related_name='threads', db_column=b'extension_version_id', to='extensions.ExtensionVersion', null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='communicationthread',
            name='_addon',
            field=models.ForeignKey(related_name='threads', db_column=b'addon_id', to='webapps.Webapp', null=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='communicationthread',
            unique_together=set([('_addon', '_version'), ('_extension', '_extension_version')]),
        ),
    ]
