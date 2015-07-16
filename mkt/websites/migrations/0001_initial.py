# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.models
import django_extensions.db.fields.json
import mkt.translations.fields
import django.db.models.deletion
from django.conf import settings
import mkt.api.fields


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tags', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Website',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('moz_id', models.PositiveIntegerField(unique=True, null=True, blank=True)),
                ('default_locale', models.CharField(default=b'en-US', max_length=10)),
                ('url', models.URLField(max_length=255, null=True, blank=True)),
                ('mobile_url', models.URLField(max_length=255, null=True, blank=True)),
                ('preferred_regions', django_extensions.db.fields.json.JSONField()),
                ('categories', django_extensions.db.fields.json.JSONField()),
                ('devices', django_extensions.db.fields.json.JSONField()),
                ('icon_type', models.CharField(max_length=25, blank=True)),
                ('icon_hash', models.CharField(max_length=8, blank=True)),
                ('last_updated', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('promo_img_hash', models.CharField(max_length=8, null=True, blank=True)),
                ('status', models.PositiveIntegerField(default=0, choices=[(0, 'Incomplete'), (16, 'Unlisted'), (2, 'Pending approval'), (4, 'Published'), (5, 'Banned from Marketplace'), (11, 'Deleted'), (12, 'Rejected'), (13, 'Approved but private'), (15, 'Blocked')])),
                ('is_disabled', models.BooleanField(default=False)),
                ('description', mkt.translations.fields.TranslatedField(related_name='Website_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
                ('keywords', models.ManyToManyField(to='tags.Tag')),
                ('name', mkt.translations.fields.TranslatedField(related_name='Website_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
                ('short_name', mkt.translations.fields.TranslatedField(related_name='Website_short_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'short_name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
                ('title', mkt.translations.fields.TranslatedField(related_name='Website_title_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'title', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
            ],
            options={
                'ordering': ('-last_updated',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WebsitePopularity',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('value', models.FloatField(default=0.0)),
                ('region', models.PositiveIntegerField(default=0, db_index=True)),
                ('website', models.ForeignKey(related_name='popularity', to='websites.Website')),
            ],
            options={
                'db_table': 'websites_popularity',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WebsiteSubmission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('modified', models.DateTimeField(auto_now=True, db_index=True)),
                ('keywords', django_extensions.db.fields.json.JSONField()),
                ('categories', django_extensions.db.fields.json.JSONField()),
                ('date_approved', models.DateTimeField(null=True, blank=True)),
                ('detected_icon', models.URLField(max_length=255, blank=True)),
                ('icon_type', models.CharField(max_length=25, null=True, blank=True)),
                ('icon_hash', models.CharField(max_length=8, null=True, blank=True)),
                ('url', models.URLField(max_length=255)),
                ('canonical_url', models.URLField(max_length=255, null=True, blank=True)),
                ('works_well', mkt.api.fields.IntegerRangeField()),
                ('public_credit', models.BooleanField(default=False)),
                ('why_relevant', models.TextField()),
                ('preferred_regions', django_extensions.db.fields.json.JSONField(null=True, blank=True)),
                ('approved', models.BooleanField(default=False, db_index=True)),
                ('description', mkt.translations.fields.TranslatedField(related_name='WebsiteSubmission_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
                ('name', mkt.translations.fields.TranslatedField(related_name='WebsiteSubmission_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True)),
                ('submitter', models.ForeignKey(related_name='websites_submitted', blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'ordering': ('-modified',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WebsiteTrending',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('value', models.FloatField(default=0.0)),
                ('region', models.PositiveIntegerField(default=0, db_index=True)),
                ('website', models.ForeignKey(related_name='trending', to='websites.Website')),
            ],
            options={
                'db_table': 'websites_trending',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='websitetrending',
            unique_together=set([('website', 'region')]),
        ),
        migrations.AlterUniqueTogether(
            name='websitepopularity',
            unique_together=set([('website', 'region')]),
        ),
    ]
