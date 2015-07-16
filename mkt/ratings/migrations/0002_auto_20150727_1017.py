# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.fields
import django.db.models.deletion
from django.conf import settings
import mkt.translations.models


class Migration(migrations.Migration):

    dependencies = [
        ('ratings', '0001_initial'),
        ('translations', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('versions', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='review',
            name='addon',
            field=models.ForeignKey(related_name='_reviews', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='review',
            name='body',
            field=mkt.translations.fields.TranslatedField(related_name='Review_body_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'body', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=False, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='review',
            name='reply_to',
            field=models.ForeignKey(related_name='replies', null=True, db_column=b'reply_to', to='ratings.Review', unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='review',
            name='title',
            field=mkt.translations.fields.TranslatedField(related_name='Review_title_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'title', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=False, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='review',
            name='user',
            field=models.ForeignKey(related_name='_reviews_all', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='review',
            name='version',
            field=models.ForeignKey(related_name='reviews', to='versions.Version', null=True),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='review',
            unique_together=set([('version', 'user', 'reply_to')]),
        ),
        migrations.AlterIndexTogether(
            name='review',
            index_together=set([('addon', 'reply_to', 'is_latest', 'created'), ('addon', 'reply_to', 'lang')]),
        ),
    ]
