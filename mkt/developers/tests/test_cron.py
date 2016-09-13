# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_

import mkt
from mkt.developers.cron import (exclude_new_region, process_iarc_changes,
                                 send_new_region_emails)
from mkt.site.tests import TestCase, WebappTestCase


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


class TestIARCChangesCron(TestCase):
    @mock.patch('mkt.developers.cron.get_rating_changes')
    def test_get_ratings_changes_is_called(self, get_rating_changes_mock):
        process_iarc_changes()
        eq_(get_rating_changes_mock.call_count, 1)
        eq_(get_rating_changes_mock.call_args[0], ())
        eq_(get_rating_changes_mock.call_args[1], {'date': None})

        get_rating_changes_mock.reset_mock()
        start_date = self.days_ago(1)
        process_iarc_changes(start_date)
        eq_(get_rating_changes_mock.call_count, 1)
        eq_(get_rating_changes_mock.call_args[0], ())
        eq_(get_rating_changes_mock.call_args[1], {'date': start_date})
