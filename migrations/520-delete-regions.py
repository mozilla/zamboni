#!/usr/bin/env python

from celery import task

from mkt.site.decorators import use_master
from mkt.webapps.models import AddonExcludedRegion


@task
@use_master
def _task(**kw):
    # 3 - Canada
    # 5 - Australia
    # 6 - New Zealand
    AddonExcludedRegion.objects.filter(region__in=[3, 5, 6]).delete()


def run():
    """Mark mobile-compatible apps as compatible for Firefox OS as well."""
    _task()
