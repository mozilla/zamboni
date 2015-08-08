# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('comm', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('versions', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='communicationthread',
            name='_addon',
            field=models.ForeignKey(related_name='threads', db_column=b'addon_id', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='communicationthread',
            name='_version',
            field=models.ForeignKey(related_name='threads', db_column=b'version_id', to='versions.Version', null=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='communicationthread',
            unique_together=set([('_addon', '_version')]),
        ),
        migrations.AddField(
            model_name='communicationnote',
            name='author',
            field=models.ForeignKey(related_name='comm_notes', blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='communicationnote',
            name='thread',
            field=models.ForeignKey(related_name='notes', to='comm.CommunicationThread'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='commattachment',
            name='note',
            field=models.ForeignKey(related_name='attachments', to='comm.CommunicationNote'),
            preserve_default=True,
        ),
    ]
