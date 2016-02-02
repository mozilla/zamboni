# -*- coding: utf-8 -*-
import mock
from nose.tools import eq_, ok_

import mkt
import mkt.site.tests
from mkt.developers.management.commands import (cleanup_addon_premium,
                                                exclude_unrated,
                                                refresh_iarc_ratings)
from mkt.site.fixtures import fixture
from mkt.webapps.models import (AddonPremium, IARCCert,
                                IARCInfo, RatingDescriptors, Webapp)


class TestCommandViews(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)

    def test_cleanup_addonpremium(self):
        self.make_premium(self.webapp)
        eq_(AddonPremium.objects.all().count(), 1)

        cleanup_addon_premium.Command().handle()
        eq_(AddonPremium.objects.all().count(), 1)

        self.webapp.update(premium_type=mkt.ADDON_FREE)
        cleanup_addon_premium.Command().handle()
        eq_(AddonPremium.objects.all().count(), 0)


@mock.patch('mkt.developers.management.commands.exclude_unrated.index_webapps')
class TestExcludeUnrated(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)

    def _germany_listed(self):
        return not self.webapp.geodata.reload().region_de_iarc_exclude

    def _brazil_listed(self):
        return not self.webapp.geodata.reload().region_br_iarc_exclude

    def test_exclude_unrated(self, index_mock):
        exclude_unrated.Command().handle()
        assert not self._brazil_listed()
        assert not self._germany_listed()

    def test_dont_exclude_rated(self, index_mock):
        mkt.site.tests.make_rated(self.webapp)

        exclude_unrated.Command().handle()
        assert self._brazil_listed()
        assert self._germany_listed()

    def test_germany_case_generic(self, index_mock):
        self.webapp.set_content_ratings({
            mkt.ratingsbodies.GENERIC: mkt.ratingsbodies.GENERIC_18
        })

        exclude_unrated.Command().handle()
        assert not self._germany_listed()
        assert not self._brazil_listed()

    def test_germany_case_usk(self, index_mock):
        self.webapp.set_content_ratings({
            mkt.ratingsbodies.USK: mkt.ratingsbodies.USK_18
        })

        exclude_unrated.Command().handle()
        assert self._germany_listed()
        assert not self._brazil_listed()

    def test_brazil_case_classind(self, index_mock):
        self.webapp.set_content_ratings({
            mkt.ratingsbodies.CLASSIND: mkt.ratingsbodies.CLASSIND_L
        })

        exclude_unrated.Command().handle()
        assert self._brazil_listed()
        assert not self._germany_listed()

    def test_index_called(self, index_mock):
        exclude_unrated.Command().handle()
        assert not self._brazil_listed()
        assert not self._germany_listed()
        assert index_mock.called
        eq_(index_mock.call_args[0][0], [self.webapp.id])


class TestRefreshIARCRatings(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.webapp = Webapp.objects.get(pk=337141)

    def test_refresh_create(self):
        IARCInfo.objects.create(
            addon=self.webapp, submission_id=52, security_code='FZ32CU8')
        refresh_iarc_ratings.Command().handle()

        ok_(self.webapp.rating_descriptors)
        ok_(self.webapp.rating_interactives)
        ok_(self.webapp.content_ratings.count())

    def test_refresh_update(self):
        IARCInfo.objects.create(
            addon=self.webapp, submission_id=52, security_code='FZ32CU8')
        rd = RatingDescriptors.objects.create(
            addon=self.webapp, has_usk_violence=True)
        refresh_iarc_ratings.Command().handle()

        ok_(rd.reload().has_esrb_strong_lang)
        ok_(not rd.has_usk_violence)

    def test_no_cert_no_refresh(self):
        refresh_iarc_ratings.Command().handle()
        ok_(not self.webapp.content_ratings.count())

    def test_single_app(self):
        IARCInfo.objects.create(
            addon=self.webapp, submission_id=52, security_code='FZ32CU8')
        refresh_iarc_ratings.Command().handle(apps=unicode(self.webapp.id))
        ok_(self.webapp.content_ratings.count())


class TestRefreshIARCRatingsV2(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestRefreshIARCRatingsV2, self).setUp()
        self.create_switch('iarc-upgrade-v2')
        self.app = Webapp.objects.get(pk=337141)

    @mock.patch('mkt.developers.management.commands.refresh_iarc_ratings'
                '.refresh_iarc_ratings.delay')
    def test_refresh_has_cert(self, refresh_iarc_ratings_delay_mock):
        IARCCert.objects.create(
            app=self.app, cert_id='e7611f4093304719aa10902ecbaf1aa4')

        refresh_iarc_ratings.Command().handle()
        eq_(refresh_iarc_ratings_delay_mock.call_count, 1)
        eq_(refresh_iarc_ratings_delay_mock.call_args[0], ([self.app.pk], ))

    @mock.patch('mkt.developers.management.commands.refresh_iarc_ratings'
                '.refresh_iarc_ratings.delay')
    def test_refresh_does_not_have_cert(self, refresh_iarc_ratings_delay_mock):
        refresh_iarc_ratings.Command().handle()
        eq_(refresh_iarc_ratings_delay_mock.call_count, 0)

        # Having IARCInfo objects should not matter, if we have no IARCCert,
        # we can't refresh ratings.
        IARCInfo.objects.create(
            addon=self.app, submission_id=52, security_code='FZ32CU8')
        refresh_iarc_ratings.Command().handle()
        eq_(refresh_iarc_ratings_delay_mock.call_count, 0)
