# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('rating', models.PositiveSmallIntegerField(null=True)),
                ('lang', models.CharField(max_length=5, null=True, editable=False, blank=True)),
                ('ip_address', models.CharField(default=b'0.0.0.0', max_length=255)),
                ('editorreview', models.BooleanField(default=False)),
                ('flag', models.BooleanField(default=False)),
                ('deleted', models.BooleanField(default=False)),
                ('is_latest', models.BooleanField(default=True, help_text=b"Is this the user's latest review for the add-on?", editable=False)),
                ('previous_count', models.PositiveIntegerField(default=0, help_text=b'How many previous reviews by the user for this add-on?', editable=False)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'reviews',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ReviewFlag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True, db_index=True)),
                ('flag', models.CharField(default=b'review_flag_reason_other', max_length=64, db_column=b'flag_name', choices=[(b'review_flag_reason_spam', 'Spam or otherwise non-review content'), (b'review_flag_reason_language', 'Inappropriate language/dialog'), (b'review_flag_reason_bug_support', 'Misplaced bug report or support request'), (b'review_flag_reason_other', 'Other (please specify)')])),
                ('note', models.CharField(default=b'', max_length=100, db_column=b'flag_notes', blank=True)),
                ('review', models.ForeignKey(to='ratings.Review')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'db_table': 'reviews_moderation_flags',
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='reviewflag',
            unique_together=set([('review', 'user')]),
        ),
    ]
