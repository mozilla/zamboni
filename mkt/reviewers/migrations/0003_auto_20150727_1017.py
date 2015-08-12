# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.models
import mkt.translations.fields
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('websites', '0001_initial'),
        ('reviewers', '0002_auto_20150727_1017'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewerscore',
            name='website',
            field=models.ForeignKey(related_name='+', blank=True, to='websites.Website', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='rereviewqueue',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='escalationqueue',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='editorsubscription',
            name='addon',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='editorsubscription',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='cannedresponse',
            name='name',
            field=mkt.translations.fields.TranslatedField(related_name='CannedResponse_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='cannedresponse',
            name='response',
            field=mkt.translations.fields.TranslatedField(related_name='CannedResponse_response_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'response', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=False, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='additionalreview',
            name='app',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='additionalreview',
            name='reviewer',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='additionalreview',
            unique_together=set([('queue', 'created')]),
        ),
    ]
