#!/usr/bin/env python
from mkt.constants import regions
from mkt.developers.cron import exclude_new_region

def run():
    exclude_new_region([regions.RU])
