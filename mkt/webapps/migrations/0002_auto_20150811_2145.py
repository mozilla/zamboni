# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mkt.constants.applications
import mkt.users.models
from django.conf import settings
import mkt.constants.regions


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webapps', '0002_webapp_hosted_url'),
        ('comm', '0002_auto_20150727_1017'),
        ('developers', '0003_auto_20150727_1017'),
        ('feed', '0002_auto_20150727_1017'),
        ('inapp', '0003_inappproduct_webapp'),
        ('prices', '0003_auto_20150727_1017'),
        ('purchase', '0002_auto_20150727_1017'),
        ('ratings', '0002_auto_20150727_1017'),
        ('reviewers', '0003_auto_20150727_1017'),
        ('submit', '0002_appsubmissionchecklist_addon'),
        ('versions', '0002_auto_20150727_1017'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='AddonUpsell',
            new_name='WebappUpsell',
        ),
        migrations.RenameModel(
            old_name='AddonDeviceType',
            new_name='WebappDeviceType',
        ),
        migrations.RenameField(
            model_name='webappdevicetype',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameModel(
            old_name='AddonExcludedRegion',
            new_name='WebappExcludedRegion',
        ),
        migrations.RenameField(
            model_name='WebappExcludedRegion',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.AlterField(
            model_name='webappexcludedregion',
            name='webapp',
            field=models.ForeignKey(related_name='webappexcludedregion', to='webapps.Webapp'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='webappexcludedregion',
            unique_together=set([('webapp', 'region')]),
        ),
        migrations.AlterUniqueTogether(
            name='webappdevicetype',
            unique_together=set([('webapp', 'device_type')]),
        ),
        migrations.RenameField(
            model_name='contentrating',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='geodata',
            new_name='webapp',
            old_name='addon',
        ),
        migrations.RenameField(
            model_name='iarcinfo',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='installed',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='installs',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='preview',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='ratingdescriptors',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='ratinginteractives',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RenameField(
            model_name='trending',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.RemoveField(
            model_name='webapp',
            name='authors',
        ),
        migrations.RenameModel(
            old_name='AddonUser',
            new_name='WebappUser',
        ),
        migrations.RenameField(
            model_name='webappuser',
            old_name='addon',
            new_name='webapp',
        ),
        migrations.AlterUniqueTogether(
            name='contentrating',
            unique_together=set([('webapp', 'ratings_body')]),
        ),
        migrations.AlterUniqueTogether(
            name='installed',
            unique_together=set([('webapp', 'user', 'install_type')]),
        ),
        migrations.AlterUniqueTogether(
            name='installs',
            unique_together=set([('webapp', 'region')]),
        ),
        migrations.AlterUniqueTogether(
            name='trending',
            unique_together=set([('webapp', 'region')]),
        ),
        migrations.AlterIndexTogether(
            name='preview',
            index_together=set([('webapp', 'position', 'created')]),
        ),
        migrations.AlterModelTable(
            name='appfeatures',
            table='webapps_features',
        ),
        migrations.AlterModelTable(
            name='blockedslug',
            table='webapps_blocked_slug',
        ),
        migrations.AlterModelTable(
            name='installs',
            table='webapps_installs',
        ),
        migrations.AlterModelTable(
            name='trending',
            table='webapps_trending',
        ),
        migrations.AlterModelTable(
            name='webapp',
            table='webapps',
        ),
        migrations.AlterModelTable(
            name='webappdevicetype',
            table='webapps_devicetypes',
        ),
        migrations.AlterModelTable(
            name='webappupsell',
            table='webapp_upsell',
        ),
        migrations.AlterModelTable(
            name='webappexcludedregion',
            table='webapps_excluded_regions',
        ),
        migrations.AlterModelTable(
            name='webappuser',
            table='webapps_users',
        ),
    ]
