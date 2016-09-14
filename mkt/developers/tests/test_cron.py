# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_

import mkt
from mkt.developers.cron import exclude_new_region, send_new_region_emails
from mkt.site.tests import WebappTestCase


class TestSendNewRegionEmails(WebappTestCase):

    @mock.patch('mkt.developers.cron._region_email')
    def test_called(self, _region_email_mock):
        eq_(self.app.enable_new_regions, True)
        send_new_region_emails([mkt.regions.GBR])
        eq_(list(_region_email_mock.call_args_list[0][0][0]), [self.app.id])

    @mock.patch('mkt.developers.cron._region_email')
    def test_not_called_with_exclusions(self, _region_email_mock):
        self.app.addonexcludedregion.create(region=mkt.regions.GBR.id)
        send_new_region_emails([mkt.regions.GBR])
        eq_(list(_region_email_mock.call_args_list[0][0][0]), [])

    @mock.patch('mkt.developers.cron._region_email')
    def test_not_called_with_enable_new_regions_false(self,
                                                      _region_email_mock):
        """Check enable_new_regions is False by default."""
        self.app.update(enable_new_regions=False)
        send_new_region_emails([mkt.regions.GBR])
        eq_(list(_region_email_mock.call_args_list[0][0][0]), [])


class TestExcludeNewRegion(WebappTestCase):

    @mock.patch('mkt.developers.cron._region_exclude')
    def test_not_called_enable_new_regions_true(self, _region_exclude_mock):
        eq_(self.app.enable_new_regions, True)
        exclude_new_region([mkt.regions.GBR])
        eq_(list(_region_exclude_mock.call_args_list[0][0][0]), [])

    @mock.patch('mkt.developers.cron._region_exclude')
    def test_not_called_with_ordinary_exclusions(self, _region_exclude_mock):
        self.app.addonexcludedregion.create(region=mkt.regions.GBR.id)
        exclude_new_region([mkt.regions.GBR])
        eq_(list(_region_exclude_mock.call_args_list[0][0][0]), [])

    @mock.patch('mkt.developers.cron._region_exclude')
    def test_called_with_enable_new_regions_false(self, _region_exclude_mock):
        # Check enable_new_regions is False by default.
        self.app.update(enable_new_regions=False)
        exclude_new_region([mkt.regions.GBR])
        eq_(list(_region_exclude_mock.call_args_list[0][0][0]), [self.app.id])
