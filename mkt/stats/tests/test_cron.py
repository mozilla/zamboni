import datetime

import mock
from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.constants.regions import REGIONS_CHOICES_SLUG
from mkt.ratings.models import Review
from mkt.site.tests import user_factory
from mkt.stats import tasks
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import AddonUser, Webapp


class TestMonolithStats(mkt.site.tests.TestCase):

    @mock.patch('mkt.stats.tasks.MonolithRecord')
    def test_mmo_user_total_count_updates_monolith(self, record):
        UserProfile.objects.create(source=mkt.LOGIN_SOURCE_MMO_BROWSERID)
        metric = 'mmo_user_count_total'

        tasks.update_monolith_stats(metric, datetime.date.today())
        self.assertTrue(record.objects.create.called)
        eq_(record.objects.create.call_args[1]['value'], '{"count": 1}')

    def test_app_new(self):
        Webapp.objects.create()
        eq_(tasks._get_monolith_jobs()['apps_count_new'][0]['count'](), 1)

    def test_app_added_counts(self):
        today = datetime.date(2013, 1, 25)
        app = Webapp.objects.create()
        app.update(created=today)

        package_type = 'packaged' if app.is_packaged else 'hosted'
        premium_type = mkt.ADDON_PREMIUM_API[app.premium_type]

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
        app = Webapp.objects.create()
        app.update(_current_version=Version.objects.create(addon=app,
                                                           reviewed=today),
                   status=mkt.STATUS_PUBLIC, created=today)
        # Create a couple more to test the counts.
        app2 = Webapp.objects.create()
        app2.update(_current_version=Version.objects.create(addon=app2,
                                                            reviewed=today),
                    status=mkt.STATUS_PENDING, created=today)
        app3 = Webapp.objects.create(disabled_by_user=True)
        app3.update(_current_version=Version.objects.create(addon=app3,
                                                            reviewed=today),
                    status=mkt.STATUS_PUBLIC, created=today)

        package_type = 'packaged' if app.is_packaged else 'hosted'
        premium_type = mkt.ADDON_PREMIUM_API[app.premium_type]

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
        addon = Webapp.objects.create()
        Review.objects.create(addon=addon, user=user_factory(), rating=5)
        eq_(tasks._get_monolith_jobs()['apps_review_count_new'][0]['count'](),
            1)

    def test_user_total(self):
        day = datetime.date(2009, 1, 1)
        p = user_factory(source=mkt.LOGIN_SOURCE_MMO_BROWSERID)
        p.update(created=day)
        jobs = tasks._get_monolith_jobs
        eq_(jobs(day)['mmo_user_count_total'][0]['count'](), 1)
        eq_(jobs()['mmo_user_count_total'][0]['count'](), 1)
        eq_(jobs()['mmo_user_count_new'][0]['count'](), 0)

    def test_user_new(self):
        user_factory(source=mkt.LOGIN_SOURCE_MMO_BROWSERID)
        eq_(tasks._get_monolith_jobs()['mmo_user_count_new'][0]['count'](), 1)

    def test_dev_total(self):
        p1 = user_factory(source=mkt.LOGIN_SOURCE_MMO_BROWSERID)
        p2 = user_factory(source=mkt.LOGIN_SOURCE_MMO_BROWSERID)
        a1 = mkt.site.tests.app_factory()
        AddonUser.objects.create(addon=a1, user=p1)
        AddonUser.objects.create(addon=a1, user=p2)

        eq_(tasks._get_monolith_jobs()
            ['mmo_developer_count_total'][0]['count'](), 2)
