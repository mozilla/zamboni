#!/usr/bin/env python

from mkt.constants import regions
from mkt.developers.cron import exclude_new_region


def run():
    exclude_new_region([
        regions.BWA, regions.CIV, regions.CMR, regions.EGY, regions.GNB,
        regions.JOR, regions.LTU, regions.MDG, regions.MLI, regions.MMR,
        regions.MUS, regions.NER, regions.SEN, regions.TUN, regions.TZA,
        regions.VUT])
