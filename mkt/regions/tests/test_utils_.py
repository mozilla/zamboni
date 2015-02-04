# -*- coding: utf-8 -*-
from nose.tools import eq_

from mkt.constants import regions
from mkt.regions.utils import parse_region, remove_accents


def test_parse_region():
    eq_(parse_region('restofworld'), regions.RESTOFWORLD)
    eq_(parse_region('br'), regions.BRA)
    eq_(parse_region('brazil'), regions.BRA)
    eq_(parse_region('bRaZiL'), regions.BRA)
    eq_(parse_region('7'), regions.BRA)
    eq_(parse_region(7), regions.BRA)
    eq_(parse_region(regions.BRA), regions.BRA)
    eq_(parse_region(''), None)


def test_parse_worldwide_region_as_restofworld():
    eq_(parse_region('worldwide'), regions.RESTOFWORLD)


def test_remove_accents():
    eq_(remove_accents(u'café'), u'cafe')
    eq_(remove_accents(u'Équateur'), u'Equateur')
    eq_(remove_accents(u'Pérou'), u'Perou')
    eq_(remove_accents(u'Węgry'), u'Wegry')
    # This hits the limitations of what's possible with built-in
    # functions but shows that if the diacritic isn't found the
    # string remains un-molested.
    eq_(remove_accents(u'Włochy'), u'Włochy')
