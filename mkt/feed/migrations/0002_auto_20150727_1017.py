# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.translations.fields
import django.db.models.deletion
import mkt.translations.models


class Migration(migrations.Migration):

    dependencies = [
        ('translations', '__first__'),
        ('feed', '0001_initial'),
        ('webapps', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedshelfmembership',
            name='app',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedshelfmembership',
            name='group',
            field=mkt.translations.fields.PurifiedField(related_name='FeedShelfMembership_group_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'group', to_field=b'id', blank=True, to=mkt.translations.models.PurifiedTranslation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedshelfmembership',
            name='obj',
            field=models.ForeignKey(to='feed.FeedShelf'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='feedshelfmembership',
            unique_together=set([('obj', 'app')]),
        ),
        migrations.AddField(
            model_name='feedshelf',
            name='_apps',
            field=models.ManyToManyField(related_name='app_shelves', through='feed.FeedShelfMembership', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedshelf',
            name='description',
            field=mkt.translations.fields.TranslatedField(related_name='FeedShelf_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedshelf',
            name='name',
            field=mkt.translations.fields.TranslatedField(related_name='FeedShelf_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feeditem',
            name='app',
            field=models.ForeignKey(blank=True, to='feed.FeedApp', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feeditem',
            name='brand',
            field=models.ForeignKey(blank=True, to='feed.FeedBrand', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feeditem',
            name='collection',
            field=models.ForeignKey(blank=True, to='feed.FeedCollection', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feeditem',
            name='shelf',
            field=models.ForeignKey(blank=True, to='feed.FeedShelf', null=True),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='feeditem',
            index_together=set([('category', 'region', 'carrier'), ('region', 'carrier')]),
        ),
        migrations.AddField(
            model_name='feedcollectionmembership',
            name='app',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedcollectionmembership',
            name='group',
            field=mkt.translations.fields.PurifiedField(related_name='FeedCollectionMembership_group_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'group', to_field=b'id', blank=True, to=mkt.translations.models.PurifiedTranslation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedcollectionmembership',
            name='obj',
            field=models.ForeignKey(to='feed.FeedCollection'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='feedcollectionmembership',
            unique_together=set([('obj', 'app')]),
        ),
        migrations.AddField(
            model_name='feedcollection',
            name='_apps',
            field=models.ManyToManyField(related_name='app_feed_collections', through='feed.FeedCollectionMembership', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedcollection',
            name='description',
            field=mkt.translations.fields.TranslatedField(related_name='FeedCollection_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedcollection',
            name='name',
            field=mkt.translations.fields.TranslatedField(related_name='FeedCollection_name_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'name', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedbrandmembership',
            name='app',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedbrandmembership',
            name='obj',
            field=models.ForeignKey(to='feed.FeedBrand'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='feedbrandmembership',
            unique_together=set([('obj', 'app')]),
        ),
        migrations.AddField(
            model_name='feedbrand',
            name='_apps',
            field=models.ManyToManyField(related_name='app_feed_brands', through='feed.FeedBrandMembership', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedapp',
            name='app',
            field=models.ForeignKey(to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedapp',
            name='description',
            field=mkt.translations.fields.TranslatedField(related_name='FeedApp_description_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'description', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedapp',
            name='preview',
            field=models.ForeignKey(blank=True, to='webapps.Preview', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedapp',
            name='pullquote_text',
            field=mkt.translations.fields.TranslatedField(related_name='FeedApp_pullquote_text_set+', null=True, on_delete=django.db.models.deletion.SET_NULL, db_column=b'pullquote_text', to_field=b'id', blank=True, to=mkt.translations.models.Translation, short=True, require_locale=True, unique=True),
            preserve_default=True,
        ),
    ]
