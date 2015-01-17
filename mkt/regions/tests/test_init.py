import mock
from nose.tools import eq_

import mkt.constants.regions as regions
from mkt.regions import get_region, set_region


@mock.patch('mkt.regions._local', None)
def test_get_region_empty():
    eq_(get_region(), regions.RESTOFWORLD)


@mock.patch('mkt.regions._local')
def test_get_region_not_empty(local):
    local.region = 'us'

    eq_(get_region(), regions.USA)


@mock.patch('mkt.regions._local')
def test_get_region_worldwide(local):
    local.region = 'worldwide'
    eq_(get_region(), regions.RESTOFWORLD)


@mock.patch('mkt.regions._local')
def test_set_region(local):
    local.region = 'us'

    eq_(get_region(), regions.USA)
    set_region('es')
    eq_(get_region(), regions.ESP)


def test_set_region_object():
    set_region(regions.USA)
    eq_(get_region(), regions.USA)
    set_region(regions.ESP)
    eq_(get_region(), regions.ESP)


def test_set_region_bad_slug():
    set_region('foo')
    eq_(get_region(), regions.RESTOFWORLD)
