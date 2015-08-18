# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reviewers', '0003_auto_20150727_1017'),
    ]

    # An incorrect constraint was added in this migration, and was removed due
    # to bug 1195292.
    operations = []
