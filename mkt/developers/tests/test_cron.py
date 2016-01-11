# -*- coding: utf-8 -*-
import datetime

import mock
from nose.tools import eq_

import mkt
from mkt.developers.cron import (_flag_rereview_adult, exclude_new_region,
                                 process_iarc_changes, send_new_region_emails)
from mkt.developers.models import ActivityLog
from mkt.site.tests import TestCase, user_factory, WebappTestCase
from mkt.site.utils import app_factory
from mkt.webapps.models import IARCInfo, RatingDescriptors, RatingInteractives


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


class TestIARCChangesCronV1(TestCase):
    @mock.patch('lib.iarc.utils.render_xml')
    def test_no_date(self, _render):
        process_iarc_changes()
        _render.assert_called_with('get_rating_changes.xml', {
            'date_from': datetime.date.today() - datetime.timedelta(days=1),
            'date_to': datetime.date.today(),
        })

    @mock.patch('lib.iarc.utils.render_xml')
    def test_with_date(self, _render):
        date = datetime.date(2001, 1, 11)
        process_iarc_changes(date.strftime('%Y-%m-%d'))
        _render.assert_called_with('get_rating_changes.xml', {
            'date_from': date - datetime.timedelta(days=1),
            'date_to': date,
        })

    def test_processing(self):
        """
        The mock client always returns the same data. Set up the app so it
        matches the submission ID and verify the data is saved as expected.
        """
        mkt.set_user(user_factory())
        app = app_factory()
        IARCInfo.objects.create(addon=app, submission_id=52,
                                security_code='FZ32CU8')
        app.set_descriptors([
            'has_classind_violence',
            'has_esrb_strong_lang',
            'has_pegi_language', 'has_pegi_online',
            'has_usk_lang',
        ])
        app.set_interactives([])
        app.set_content_ratings({
            mkt.ratingsbodies.CLASSIND: mkt.ratingsbodies.CLASSIND_L
        })

        process_iarc_changes()
        app = app.reload()

        # Check ratings. CLASSIND should get updated.
        cr = app.content_ratings.get(
            ratings_body=mkt.ratingsbodies.CLASSIND.id)
        eq_(cr.rating, mkt.ratingsbodies.CLASSIND_14.id)
        cr = app.content_ratings.get(ratings_body=mkt.ratingsbodies.ESRB.id)
        eq_(cr.rating, mkt.ratingsbodies.ESRB_M.id)

        assert ActivityLog.objects.filter(
            action=mkt.LOG.CONTENT_RATING_CHANGED.id).count()

        # Check descriptors.
        rd = RatingDescriptors.objects.get(addon=app)
        self.assertSetEqual(rd.to_keys(), [
            'has_esrb_strong_lang',
            'has_classind_lang',
            'has_pegi_lang', 'has_pegi_online',
            'has_usk_lang',
        ])

        # Check interactives.
        ri = RatingInteractives.objects.get(addon=app)
        self.assertSetEqual(ri.to_keys(), [
            'has_shares_info', 'has_shares_location', 'has_digital_purchases',
            'has_users_interact'
        ])

    def test_rereview_flag_adult(self):
        mkt.set_user(user_factory())
        app = app_factory()

        app.set_content_ratings({
            mkt.ratingsbodies.ESRB: mkt.ratingsbodies.ESRB_E,
            mkt.ratingsbodies.CLASSIND: mkt.ratingsbodies.CLASSIND_18,
        })
        _flag_rereview_adult(app, mkt.ratingsbodies.ESRB,
                             mkt.ratingsbodies.ESRB_T)
        assert not app.rereviewqueue_set.count()
        assert not ActivityLog.objects.filter(
            action=mkt.LOG.CONTENT_RATING_TO_ADULT.id).exists()

        # Adult should get flagged to rereview.
        _flag_rereview_adult(app, mkt.ratingsbodies.ESRB,
                             mkt.ratingsbodies.ESRB_A)
        eq_(app.rereviewqueue_set.count(), 1)
        eq_(ActivityLog.objects.filter(
            action=mkt.LOG.CONTENT_RATING_TO_ADULT.id).count(), 1)

        # Test things same same if rating stays the same as adult.
        app.set_content_ratings({
            mkt.ratingsbodies.ESRB: mkt.ratingsbodies.ESRB_A,
        })
        _flag_rereview_adult(app, mkt.ratingsbodies.ESRB,
                             mkt.ratingsbodies.ESRB_A)
        eq_(app.rereviewqueue_set.count(), 1)
        eq_(ActivityLog.objects.filter(
            action=mkt.LOG.CONTENT_RATING_TO_ADULT.id).count(), 1)


class TestIARCChangesCronV2(TestCase):
    def setUp(self):
        super(TestIARCChangesCronV2, self).setUp()
        self.create_switch('iarc-upgrade-v2')

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
