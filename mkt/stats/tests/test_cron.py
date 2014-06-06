import datetime

import mock
from nose.tools import eq_

import amo.tests
from addons.models import Addon, AddonUser
from reviews.models import Review
from users.models import UserProfile
from versions.models import Version

from mkt.constants.regions import REGIONS_CHOICES_SLUG
from mkt.stats import tasks


class TestMonolithStats(amo.tests.TestCase):

    @mock.patch('mkt.stats.tasks.MonolithRecord')
    def test_mmo_user_total_count_updates_monolith(self, record):
        UserProfile.objects.create(source=amo.LOGIN_SOURCE_MMO_BROWSERID)
        metric = 'mmo_user_count_total'

        tasks.update_monolith_stats(metric, datetime.date.today())
        self.assertTrue(record.objects.create.called)
        eq_(record.objects.create.call_args[1]['value'], '{"count": 1}')

    def test_app_new(self):
        Addon.objects.create(type=amo.ADDON_WEBAPP)
        eq_(tasks._get_monolith_jobs()['apps_count_new'][0]['count'](), 1)

    def test_app_added_counts(self):
        today = datetime.date(2013, 1, 25)
        app = Addon.objects.create(type=amo.ADDON_WEBAPP)
        app.update(created=today)

        package_type = 'packaged' if app.is_packaged else 'hosted'
        premium_type = amo.ADDON_PREMIUM_API[app.premium_type]

        # Add a region exclusion.
        regions = dict(REGIONS_CHOICES_SLUG)
        excluded_region = regions['br']
        app.addonexcludedregion.create(region=excluded_region.id)

        jobs = tasks._get_monolith_jobs(today)

        # Check package type counts.
        for job in jobs['apps_added_by_package_type']:
            r = job['dimensions']['region']
            p = job['dimensions']['package_type']
            if r != excluded_region.slug and p == package_type:
                expected_count = 1
            else:
                expected_count = 0
            count = job['count']()
            eq_(count, expected_count,
                'Incorrect count for region %s, package type %s. '
                'Got %d, expected %d.' % (r, p, count, expected_count))

        # Check premium type counts.
        for job in jobs['apps_added_by_premium_type']:
            r = job['dimensions']['region']
            p = job['dimensions']['premium_type']
            if r != excluded_region.slug and p == premium_type:
                expected_count = 1
            else:
                expected_count = 0
            count = job['count']()
            eq_(count, expected_count,
                'Incorrect count for region %s, premium type %s. '
                'Got %d, expected %d.' % (r, p, count, expected_count))

    def test_app_avail_counts(self):
        today = datetime.date(2013, 1, 25)
        app = Addon.objects.create(type=amo.ADDON_WEBAPP)
        app.update(_current_version=Version.objects.create(addon=app,
                                                           reviewed=today),
                   status=amo.STATUS_PUBLIC, created=today)
        # Create a couple more to test the counts.
        app2 = Addon.objects.create(type=amo.ADDON_WEBAPP)
        app2.update(_current_version=Version.objects.create(addon=app2,
                                                            reviewed=today),
                    status=amo.STATUS_PENDING, created=today)
        app3 = Addon.objects.create(type=amo.ADDON_WEBAPP, disabled_by_user=True)
        app3.update(_current_version=Version.objects.create(addon=app3,
                                                            reviewed=today),
                    status=amo.STATUS_PUBLIC, created=today)

        package_type = 'packaged' if app.is_packaged else 'hosted'
        premium_type = amo.ADDON_PREMIUM_API[app.premium_type]

        # Add a region exclusion.
        regions = dict(REGIONS_CHOICES_SLUG)
        excluded_region = regions['br']
        app.addonexcludedregion.create(region=excluded_region.id)

        jobs = tasks._get_monolith_jobs(today)

        # Check package type counts.
        for job in jobs['apps_available_by_package_type']:
            r = job['dimensions']['region']
            p = job['dimensions']['package_type']
            if r != excluded_region.slug and p == package_type:
                expected_count = 1
            else:
                expected_count = 0
            count = job['count']()
            eq_(count, expected_count,
                'Incorrect count for region %s, package type %s. '
                'Got %d, expected %d.' % (r, p, count, expected_count))

        # Check premium type counts.
        for job in jobs['apps_available_by_premium_type']:
            r = job['dimensions']['region']
            p = job['dimensions']['premium_type']
            if r != excluded_region.slug and p == premium_type:
                expected_count = 1
            else:
                expected_count = 0
            count = job['count']()
            eq_(count, expected_count,
                'Incorrect count for region %s, premium type %s. '
                'Got %d, expected %d.' % (r, p, count, expected_count))

    def test_app_reviews(self):
        addon = Addon.objects.create(type=amo.ADDON_WEBAPP)
        user = UserProfile.objects.create(username='foo')
        Review.objects.create(addon=addon, user=user)
        eq_(tasks._get_monolith_jobs()['apps_review_count_new'][0]['count'](),
            1)

    def test_user_total(self):
        day = datetime.date(2009, 1, 1)
        p = UserProfile.objects.create(username='foo',
                                       source=amo.LOGIN_SOURCE_MMO_BROWSERID)
        p.update(created=day)
        eq_(tasks._get_monolith_jobs(day)['mmo_user_count_total'][0]['count'](),
            1)
        eq_(tasks._get_monolith_jobs()['mmo_user_count_total'][0]['count'](),
            1)
        eq_(tasks._get_monolith_jobs()['mmo_user_count_new'][0]['count'](), 0)

    def test_user_new(self):
        UserProfile.objects.create(username='foo',
                                   source=amo.LOGIN_SOURCE_MMO_BROWSERID)
        eq_(tasks._get_monolith_jobs()['mmo_user_count_new'][0]['count'](), 1)

    def test_dev_total(self):
        p1 = UserProfile.objects.create(username='foo',
                                        source=amo.LOGIN_SOURCE_MMO_BROWSERID)
        p2 = UserProfile.objects.create(username='bar',
                                        source=amo.LOGIN_SOURCE_MMO_BROWSERID)
        a1 = amo.tests.addon_factory()
        a2 = amo.tests.app_factory()
        AddonUser.objects.create(addon=a1, user=p1)
        AddonUser.objects.create(addon=a1, user=p2)
        AddonUser.objects.create(addon=a2, user=p1)

        eq_(tasks._get_monolith_jobs()['mmo_developer_count_total'][0]['count'](),
            1)
