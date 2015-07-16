# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('action', models.SmallIntegerField(db_index=True, choices=[(1, b'CREATE_ADDON'), (2, b'EDIT_PROPERTIES'), (3, b'EDIT_DESCRIPTIONS'), (4, b'EDIT_CATEGORIES'), (5, b'ADD_USER_WITH_ROLE'), (6, b'REMOVE_USER_WITH_ROLE'), (7, b'EDIT_CONTRIBUTIONS'), (8, b'USER_DISABLE'), (9, b'USER_ENABLE'), (10, b'SET_PUBLIC_STATS'), (11, b'UNSET_PUBLIC_STATS'), (12, b'CHANGE_STATUS'), (13, b'ADD_PREVIEW'), (14, b'EDIT_PREVIEW'), (15, b'DELETE_PREVIEW'), (16, b'ADD_VERSION'), (17, b'EDIT_VERSION'), (18, b'DELETE_VERSION'), (19, b'ADD_FILE_TO_VERSION'), (20, b'DELETE_FILE_FROM_VERSION'), (21, b'APPROVE_VERSION'), (22, b'RETAIN_VERSION'), (23, b'ESCALATE_VERSION'), (24, b'REQUEST_VERSION'), (25, b'ADD_TAG'), (26, b'REMOVE_TAG'), (27, b'ADD_TO_COLLECTION'), (28, b'REMOVE_FROM_COLLECTION'), (29, b'ADD_REVIEW'), (31, b'ADD_RECOMMENDED_CATEGORY'), (32, b'REMOVE_RECOMMENDED_CATEGORY'), (33, b'ADD_RECOMMENDED'), (34, b'REMOVE_RECOMMENDED'), (35, b'ADD_APPVERSION'), (36, b'CHANGE_USER_WITH_ROLE'), (38, b'CHANGE_POLICY'), (39, b'CHANGE_ICON'), (40, b'APPROVE_REVIEW'), (41, b'DELETE_REVIEW'), (42, b'PRELIMINARY_VERSION'), (43, b'REJECT_VERSION'), (44, b'REQUEST_INFORMATION'), (45, b'REQUEST_SUPER_REVIEW'), (46, b'MAX_APPVERSION_UPDATED'), (47, b'BULK_VALIDATION_EMAILED'), (48, b'CHANGE_PASSWORD'), (49, b'COMMENT_VERSION'), (50, b'MAKE_PREMIUM'), (52, b'MANIFEST_UPDATED'), (53, b'APPROVE_VERSION_PRIVATE'), (54, b'PURCHASE_ADDON'), (55, b'INSTALL_ADDON'), (56, b'REFUND_REQUESTED'), (57, b'REFUND_DECLINED'), (58, b'REFUND_GRANTED'), (59, b'REFUND_INSTANT'), (60, b'USER_EDITED'), (65, b'RECEIPT_CHECKED'), (66, b'ESCALATION_CLEARED'), (67, b'APP_DISABLED'), (68, b'ESCALATED_HIGH_ABUSE'), (69, b'ESCALATED_HIGH_REFUNDS'), (70, b'REREVIEW_MANIFEST_CHANGE'), (71, b'REREVIEW_PREMIUM_TYPE_UPGRADE'), (72, b'REREVIEW_CLEARED'), (73, b'ESCALATE_MANUAL'), (74, b'VIDEO_ERROR'), (75, b'REREVIEW_DEVICES_ADDED'), (76, b'REVIEW_DEVICE_OVERRIDE'), (77, b'WEBAPP_RESUBMIT'), (78, b'ESCALATION_VIP_APP'), (79, b'REREVIEW_MANIFEST_URL_CHANGE'), (80, b'ESCALATION_PRERELEASE_APP'), (81, b'REREVIEW_ABUSE_APP'), (82, b'REREVIEW_MANUAL'), (98, b'CUSTOM_TEXT'), (99, b'CUSTOM_HTML'), (100, b'OBJECT_ADDED'), (101, b'OBJECT_EDITED'), (102, b'OBJECT_DELETED'), (103, b'ADMIN_USER_EDITED'), (104, b'ADMIN_USER_ANONYMIZED'), (105, b'ADMIN_USER_RESTRICTED'), (106, b'ADMIN_VIEWED_LOG'), (107, b'EDIT_REVIEW'), (108, b'THEME_REVIEW'), (120, b'GROUP_USER_ADDED'), (121, b'GROUP_USER_REMOVED'), (122, b'REVIEW_FEATURES_OVERRIDE'), (123, b'REREVIEW_FEATURES_CHANGED'), (124, b'CHANGE_VERSION_STATUS'), (125, b'DELETE_USER_LOOKUP'), (126, b'CONTENT_RATING_TO_ADULT'), (127, b'CONTENT_RATING_CHANGED'), (128, b'PRIORITY_REVIEW_REQUESTED'), (129, b'PASS_ADDITIONAL_REVIEW'), (130, b'BULK_VALIDATION_USER_EMAILED'), (130, b'FAIL_ADDITIONAL_REVIEW'), (131, b'APP_ABUSE_MARKREAD'), (132, b'WEBSITE_ABUSE_MARKREAD')])),
                ('_arguments', models.TextField(db_column=b'arguments', blank=True)),
                ('_details', models.TextField(db_column=b'details', blank=True)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ActivityLogAttachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('filepath', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=255, blank=True)),
                ('mimetype', models.CharField(max_length=255, blank=True)),
            ],
            options={
                'ordering': ('id',),
                'db_table': 'log_activity_attachment',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='AddonPaymentAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('account_uri', models.CharField(max_length=255)),
                ('product_uri', models.CharField(unique=True, max_length=255)),
            ],
            options={
                'db_table': 'addon_payment_account',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='AppLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity_app',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='CommentLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('comments', models.CharField(max_length=255)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity_comment',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='GroupLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity_group',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='PaymentAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=64)),
                ('agreed_tos', models.BooleanField(default=False)),
                ('seller_uri', models.CharField(unique=True, max_length=255)),
                ('uri', models.CharField(unique=True, max_length=255)),
                ('inactive', models.BooleanField(default=False)),
                ('account_id', models.CharField(max_length=255)),
                ('provider', models.IntegerField(default=1, choices=[(0, b'paypal'), (1, b'bango'), (2, b'reference')])),
                ('shared', models.BooleanField(default=False)),
            ],
            options={
                'db_table': 'payment_accounts',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='PreloadTestPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('last_submission', models.DateTimeField(auto_now_add=True)),
                ('filename', models.CharField(max_length=60)),
                ('status', models.PositiveSmallIntegerField(default=4)),
            ],
            options={
                'ordering': ['-last_submission'],
                'db_table': 'preload_test_plans',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SolitudeSeller',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('uuid', models.CharField(unique=True, max_length=255)),
                ('resource_uri', models.CharField(max_length=255)),
            ],
            options={
                'db_table': 'payments_seller',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='UserInappKey',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('seller_product_pk', models.IntegerField(unique=True)),
            ],
            options={
                'db_table': 'user_inapp_keys',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='UserLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity_user',
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='VersionLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('activity_log', models.ForeignKey(to='developers.ActivityLog')),
            ],
            options={
                'ordering': ('-created',),
                'db_table': 'log_activity_version',
            },
            bases=(models.Model,),
        ),
    ]
