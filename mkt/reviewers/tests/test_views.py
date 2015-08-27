# -*- coding: utf-8 -*-
import json
import re
import time
from datetime import datetime, timedelta
from itertools import cycle
from os import path

from django import test
from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.utils import translation

import mock
import requests
import waffle
from cache_nuggets.lib import Token
from jingo.helpers import urlparams
from nose import SkipTest
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq
from requests.structures import CaseInsensitiveDict

import mkt
import mkt.ratings
import mkt.site.tests
from lib.crypto import packaged
from lib.crypto.tests import mock_sign
from mkt.abuse.models import AbuseReport
from mkt.api.tests.test_oauth import RestOAuth
from mkt.comm.tests.test_views import CommTestMixin
from mkt.comm.utils import create_comm_note
from mkt.constants import MANIFEST_CONTENT_TYPE, comm
from mkt.developers.models import ActivityLog, AppLog
from mkt.files.models import File
from mkt.ratings.models import Review, ReviewFlag
from mkt.reviewers.models import (QUEUE_TARAKO, CannedResponse,
                                  EscalationQueue, RereviewQueue,
                                  ReviewerScore)
from mkt.reviewers.utils import ReviewersQueuesHelper
from mkt.reviewers.views import (_progress, app_review, queue_apps,
                                 route_reviewer)
from mkt.site.fixtures import fixture
from mkt.site.helpers import absolutify, isotime
from mkt.site.storage_utils import private_storage, public_storage
from mkt.site.tests import (check_links, days_ago, formset, initial,
                            req_factory_factory, user_factory)
from mkt.site.utils import app_factory, make_game, paginate, version_factory
from mkt.submit.tests.test_views import BasePackagedAppTest, SetupFilesMixin
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import AddonDeviceType, Webapp
from mkt.webapps.tasks import unindex_webapps
from mkt.websites.utils import website_factory
from mkt.zadmin.models import get_config, set_config


TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TEST_PATH = path.dirname(path.abspath(__file__))
ATTACHMENTS_DIR = path.abspath(path.join(TEST_PATH, '..', '..', 'comm',
                                         'tests', 'attachments'))


class AttachmentManagementMixin(object):

    def _attachment_management_form(self, num=1):
        """
        Generate and return data for a management form for `num` attachments
        """
        return {'attachment-TOTAL_FORMS': max(1, num),
                'attachment-INITIAL_FORMS': 0,
                'attachment-MAX_NUM_FORMS': 1000}

    def _attachments(self, num):
        """Generate and return data for `num` attachments """
        data = {}
        files = ['bacon.jpg', 'bacon.txt']
        descriptions = ['mmm, bacon', '']
        if num > 0:
            for n in xrange(num):
                i = 0 if n % 2 else 1
                attachment = open(path.join(ATTACHMENTS_DIR, files[i]), 'r+')
                data.update({
                    'attachment-%d-attachment' % n: attachment,
                    'attachment-%d-description' % n: descriptions[i]
                })
        return data


class TestedonManagementMixin(object):

    def _testedon_management_form(self, num=0):
        """
        Generate and return data for a management form for `num` tested on
        platforms.
        """
        return {'testedon-TOTAL_FORMS': max(1, num),
                'testedon-INITIAL_FORMS': 0,
                'testedon-MAX_NUM_FORMS': 1000}

    def _platforms(self, num, device_types=[u'\xd0esktop', u'FirefoxOS'],
                   devices=[u'PC ', u'ZT\xc8 Open'],
                   versions=[u'34', u'1.3<']):
        """Generate and return data for `num` tested on platforms """
        data = {}
        if num > 0:
            for n in xrange(num):
                i = n % len(device_types)
                data.update({
                    'testedon-%d-device_type' % n: device_types[i],
                    'testedon-%d-device' % n: devices[i],
                    'testedon-%d-version' % n: versions[i],
                })
        return data


class AppReviewerTest(mkt.site.tests.TestCase):

    def setUp(self):
        super(AppReviewerTest, self).setUp()
        self.reviewer_user = user_factory(email='editor')
        self.grant_permission(self.reviewer_user, 'Apps:Review')
        self.snr_reviewer_user = user_factory(email='snrreviewer')
        self.grant_permission(self.snr_reviewer_user, 'Apps:Review,Apps:Edit,'
                              'Apps:ReviewEscalated,Apps:ReviewPrivileged',
                              name='Senior App Reviewers')
        self.admin_user = user_factory(email='admin')
        self.grant_permission(self.admin_user, '*:*')
        self.regular_user = user_factory(email='regular')
        self.contact_user = user_factory(email='contact')
        self.login_as_editor()

    def login_as_admin(self):
        self.login(self.admin_user)

    def login_as_editor(self):
        self.login(self.reviewer_user)

    def login_as_senior_reviewer(self):
        self.login(self.snr_reviewer_user)

    def check_actions(self, expected, elements):
        """Check the action buttons on the review page.

        `expected` is a list of tuples containing action name and action form
        value.  `elements` is a PyQuery list of input elements.

        """
        for idx, item in enumerate(expected):
            text, form_value = item
            e = elements.eq(idx)
            eq_(e.parent().text(), text)
            eq_(e.attr('name'), 'action')
            eq_(e.val(), form_value)

    def uses_es(self):
        return waffle.switch_is_active('reviewer-tools-elasticsearch')


class AccessMixin(object):

    def test_403_for_non_editor(self, *args, **kwargs):
        self.login('regular@mozilla.com')
        eq_(self.client.head(self.url).status_code, 403)

    def test_302_for_anonymous(self, *args, **kwargs):
        self.client.logout()
        eq_(self.client.head(self.url).status_code, 302)


class SearchMixin(object):

    def test_search_query(self):
        # Light test to make sure queues can handle search queries.
        res = self.client.get(self.url, {'text_query': 'test'})
        eq_(res.status_code, 200)


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestReviewersHome(AppReviewerTest, AccessMixin):

    def setUp(self):
        super(TestReviewersHome, self).setUp()
        self.url = reverse('reviewers.home')
        self.apps = [app_factory(name='Antelope',
                                 status=mkt.STATUS_PENDING,
                                 file_kw={'status': mkt.STATUS_PENDING}),
                     app_factory(name='Bear',
                                 status=mkt.STATUS_PENDING,
                                 file_kw={'status': mkt.STATUS_PENDING}),
                     app_factory(name='Cougar',
                                 status=mkt.STATUS_PENDING,
                                 file_kw={'status': mkt.STATUS_PENDING})]
        self.packaged_app = app_factory(name='Dinosaur',
                                        status=mkt.STATUS_PUBLIC,
                                        is_packaged=True)
        version_factory(addon=self.packaged_app,
                        file_kw={'status': mkt.STATUS_PENDING})

        # Add a disabled app for good measure.
        app_factory(name='Elephant', disabled_by_user=True,
                    status=mkt.STATUS_PENDING)

        # Escalate one app to make sure it doesn't affect stats.
        escalated = app_factory(name='Eyelash Pit Viper',
                                status=mkt.STATUS_PENDING)
        EscalationQueue.objects.create(addon=escalated)

        # Add a public app under re-review.
        rereviewed = app_factory(name='Finch', status=mkt.STATUS_PUBLIC)
        rq = RereviewQueue.objects.create(addon=rereviewed)
        rq.update(created=self.days_ago(1))

        # Add an app with latest update deleted. It shouldn't affect anything.
        app = app_factory(name='Great White Shark',
                          status=mkt.STATUS_PUBLIC,
                          version_kw={'version': '1.0'},
                          is_packaged=True)
        v = version_factory(addon=app,
                            version='2.1',
                            file_kw={'status': mkt.STATUS_PENDING})
        v.update(deleted=True)

    def test_route_reviewer(self):
        # App reviewers go to apps home.
        req = mkt.site.tests.req_factory_factory(
            reverse('reviewers'),
            user=UserProfile.objects.get(email='editor@mozilla.com'))
        r = route_reviewer(req)
        self.assert3xx(r, reverse('reviewers.home'))

    def test_progress_pending(self):
        self.apps[0].latest_version.update(nomination=self.days_ago(1))
        self.apps[1].latest_version.update(nomination=self.days_ago(8))
        self.apps[2].latest_version.update(nomination=self.days_ago(15))
        counts, percentages = _progress()
        eq_(counts['pending']['week'], 1)
        eq_(counts['pending']['new'], 1)
        eq_(counts['pending']['old'], 1)
        eq_(counts['pending']['med'], 1)
        self.assertAlmostEqual(percentages['pending']['new'], 33.333333333333)
        self.assertAlmostEqual(percentages['pending']['old'], 33.333333333333)
        self.assertAlmostEqual(percentages['pending']['med'], 33.333333333333)

    def test_progress_rereview(self):
        rq = RereviewQueue.objects.create(addon=self.apps[0])
        rq.update(created=self.days_ago(8))
        rq = RereviewQueue.objects.create(addon=self.apps[1])
        rq.update(created=self.days_ago(15))
        counts, percentages = _progress()
        eq_(counts['rereview']['week'], 1)
        eq_(counts['rereview']['new'], 1)
        eq_(counts['rereview']['old'], 1)
        eq_(counts['rereview']['med'], 1)
        self.assertAlmostEqual(percentages['rereview']['new'], 33.333333333333)
        self.assertAlmostEqual(percentages['rereview']['old'], 33.333333333333)
        self.assertAlmostEqual(percentages['rereview']['med'], 33.333333333333)

    def test_progress_updated(self):
        extra_app = app_factory(name='Jackalope',
                                status=mkt.STATUS_PUBLIC,
                                is_packaged=True,
                                created=self.days_ago(35))
        version_factory(addon=extra_app,
                        file_kw={'status': mkt.STATUS_PENDING},
                        created=self.days_ago(25),
                        nomination=self.days_ago(8))
        extra_app = app_factory(name='Jackrabbit',
                                status=mkt.STATUS_PUBLIC,
                                is_packaged=True,
                                created=self.days_ago(35))
        version_factory(addon=extra_app,
                        file_kw={'status': mkt.STATUS_PENDING},
                        created=self.days_ago(25),
                        nomination=self.days_ago(25))
        counts, percentages = _progress()
        eq_(counts['updates']['week'], 1)
        eq_(counts['updates']['new'], 1)
        eq_(counts['updates']['old'], 1)
        eq_(counts['updates']['med'], 1)
        self.assertAlmostEqual(percentages['updates']['new'], 33.333333333333)
        self.assertAlmostEqual(percentages['updates']['old'], 33.333333333333)
        self.assertAlmostEqual(percentages['updates']['med'], 33.333333333333)

    def test_stats_waiting(self):
        self.apps[0].latest_version.update(nomination=self.days_ago(1))
        self.apps[1].latest_version.update(nomination=self.days_ago(5))
        self.apps[2].latest_version.update(nomination=self.days_ago(15))
        self.packaged_app.update(created=self.days_ago(1))

        doc = pq(self.client.get(self.url).content)

        anchors = doc('.editor-stats-title a')
        eq_(anchors.eq(0).text(), '3 Pending App Reviews')
        eq_(anchors.eq(1).text(), '1 Re-review')
        eq_(anchors.eq(2).text(), '1 Update Review')

        divs = doc('.editor-stats-table > div')

        # Pending review.
        eq_(divs.eq(0).text(), '2 unreviewed app submissions this week.')

        # Re-reviews.
        eq_(divs.eq(2).text(), '1 unreviewed app submission this week.')

        # Update review.
        eq_(divs.eq(4).text(), '1 unreviewed app submission this week.')

        # Maths.
        # Pending review.
        eq_(doc('.waiting_new').eq(0).attr('title')[-3:], '33%')
        eq_(doc('.waiting_med').eq(0).attr('title')[-3:], '33%')
        eq_(doc('.waiting_old').eq(0).attr('title')[-3:], '33%')

        # Re-reviews.
        eq_(doc('.waiting_new').eq(1).attr('title')[-4:], '100%')
        eq_(doc('.waiting_med').eq(1).attr('title')[-3:], ' 0%')
        eq_(doc('.waiting_old').eq(1).attr('title')[-3:], ' 0%')

        # Update review.
        eq_(doc('.waiting_new').eq(2).attr('title')[-4:], '100%')
        eq_(doc('.waiting_med').eq(2).attr('title')[-3:], ' 0%')
        eq_(doc('.waiting_old').eq(2).attr('title')[-3:], ' 0%')

    def test_reviewer_leaders(self):
        reviewers = UserProfile.objects.all()[:2]
        # 1st user reviews 2, 2nd user only 1.
        users = cycle(reviewers)
        for app in self.apps:
            mkt.log(mkt.LOG.APPROVE_VERSION, app, app.latest_version,
                    user=users.next(), details={'comments': 'hawt'})

        doc = pq(self.client.get(self.url).content.decode('utf-8'))

        # Top Reviews.
        table = doc('#editors-stats .editor-stats-table').eq(0)
        eq_(table.find('td').eq(0).text(), reviewers[0].email)
        eq_(table.find('td').eq(1).text(), u'2')
        eq_(table.find('td').eq(2).text(), reviewers[1].email)
        eq_(table.find('td').eq(3).text(), u'1')

        # Top Reviews this month.
        table = doc('#editors-stats .editor-stats-table').eq(1)
        eq_(table.find('td').eq(0).text(), reviewers[0].email)
        eq_(table.find('td').eq(1).text(), u'2')
        eq_(table.find('td').eq(2).text(), reviewers[1].email)
        eq_(table.find('td').eq(3).text(), u'1')


class FlagsMixin(object):

    def test_flag_packaged_app(self):
        self.apps[0].update(is_packaged=True)
        if self.uses_es():
            self.reindex(Webapp)
        eq_(self.apps[0].is_packaged, True)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        td = pq(res.content)('#addon-queue tbody tr td.flags').eq(0)
        flag = td('div.sprite-reviewer-packaged-app')
        eq_(flag.length, 1)

    def test_flag_premium_app(self):
        self.apps[0].update(premium_type=mkt.ADDON_PREMIUM)
        if self.uses_es():
            self.reindex(Webapp)
        eq_(self.apps[0].is_premium(), True)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        flags = tds('div.sprite-reviewer-premium')
        eq_(flags.length, 1)

    def test_flag_free_inapp_app(self):
        self.apps[0].update(premium_type=mkt.ADDON_FREE_INAPP)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        eq_(tds('div.sprite-reviewer-premium.inapp.free').length, 1)

    def test_flag_premium_inapp_app(self):
        self.apps[0].update(premium_type=mkt.ADDON_PREMIUM_INAPP)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        eq_(tds('div.sprite-reviewer-premium.inapp').length, 1)

    def test_flag_info(self):
        self.apps[0].latest_version.update(has_info_request=True)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        flags = tds('div.sprite-reviewer-info')
        eq_(flags.length, 1)

    def test_flag_comment(self):
        self.apps[0].latest_version.update(has_editor_comment=True)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        flags = tds('div.sprite-reviewer-editor')
        eq_(flags.length, 1)


class XSSMixin(object):

    def test_xss_in_queue(self):
        a = self.apps[0]
        a.name = '<script>alert("xss")</script>'
        a.save()
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tbody = pq(res.content)('#addon-queue tbody').html()
        assert '&lt;script&gt;' in tbody
        assert '<script>' not in tbody


class TestAppQueue(AppReviewerTest, AccessMixin, FlagsMixin, SearchMixin,
                   XSSMixin):

    def setUp(self):
        super(TestAppQueue, self).setUp()
        self.apps = [app_factory(name='XXX',
                                 status=mkt.STATUS_PENDING,
                                 version_kw={'nomination': self.days_ago(2)},
                                 file_kw={'status': mkt.STATUS_PENDING}),
                     app_factory(name='YYY',
                                 status=mkt.STATUS_PENDING,
                                 version_kw={'nomination': self.days_ago(1)},
                                 file_kw={'status': mkt.STATUS_PENDING}),
                     app_factory(name='ZZZ')]
        self.apps[0].update(created=self.days_ago(12))
        self.apps[1].update(created=self.days_ago(11))

        RereviewQueue.objects.create(addon=self.apps[2])

        self.url = reverse('reviewers.apps.queue_pending')

    def tearDown(self):
        if self.uses_es():
            unindex_webapps([app.id for app in self.apps])
        super(TestAppQueue, self).tearDown()

    def review_url(self, app):
        return reverse('reviewers.apps.review', args=[app.app_slug])

    def test_queue_viewing_ping(self):
        eq_(self.client.post(reverse('reviewers.queue_viewing')).status_code,
            200)

    def test_template_links(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        links = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(2) a')
        apps = Webapp.objects.filter(
            status=mkt.STATUS_PENDING).order_by('created')
        expected = [
            (unicode(apps[0].name), self.review_url(apps[0])),
            (unicode(apps[1].name), self.review_url(apps[1])),
        ]
        check_links(expected, links, verify=False)

    def test_action_buttons_pending(self):
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Reject', 'reject'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_rejected(self):
        # Check action buttons for a previously rejected app.
        self.apps[0].update(status=mkt.STATUS_REJECTED)
        self.apps[0].latest_version.files.update(status=mkt.STATUS_DISABLED)
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    @mock.patch('mkt.versions.models.Version.is_privileged', True)
    def test_action_buttons_privileged_cantreview(self):
        self.apps[0].update(is_packaged=True)
        self.apps[0].latest_version.files.update(status=mkt.STATUS_PENDING)
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    @mock.patch('mkt.versions.models.Version.is_privileged', True)
    def test_action_buttons_privileged_canreview(self):
        self.login_as_senior_reviewer()
        self.apps[0].update(is_packaged=True)
        self.apps[0].latest_version.files.update(status=mkt.STATUS_PENDING)
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Reject', 'reject'),
            (u'Ban app', 'disable'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_devices(self):
        AddonDeviceType.objects.create(addon=self.apps[0], device_type=1)
        AddonDeviceType.objects.create(addon=self.apps[0], device_type=2)
        if self.uses_es():
            self.reindex(Webapp)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        tds = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(5)')
        eq_(tds('ul li:not(.unavailable)').length, 2)

    def test_payments(self):
        self.apps[0].update(premium_type=mkt.ADDON_PREMIUM)
        self.apps[1].update(premium_type=mkt.ADDON_FREE_INAPP)
        if self.uses_es():
            self.reindex(Webapp)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        tds = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(6)')
        eq_(tds.eq(0).text(),
            unicode(mkt.ADDON_PREMIUM_TYPES[mkt.ADDON_PREMIUM]))
        eq_(tds.eq(1).text(),
            unicode(mkt.ADDON_PREMIUM_TYPES[mkt.ADDON_FREE_INAPP]))

    def test_invalid_page(self):
        r = self.client.get(self.url, {'page': 999})
        eq_(r.status_code, 200)
        eq_(r.context['pager'].number, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (2)')
        eq_(links[1].text, u'Re-reviews (1)')
        eq_(links[2].text, u'Updates (0)')

    def test_queue_count_senior_reviewer(self):
        self.login_as_senior_reviewer()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (2)')
        eq_(links[1].text, u'Re-reviews (1)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Escalations (0)')

    def test_escalated_not_in_queue(self):
        self.login_as_senior_reviewer()
        EscalationQueue.objects.create(addon=self.apps[0])
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        # self.apps[2] is not pending so doesn't show up either.
        eq_([a.app.id for a in res.context['addons']], [self.apps[1].id])

        doc = pq(res.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (1)')
        eq_(links[1].text, u'Re-reviews (1)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Escalations (1)')

    def test_incomplete_no_in_queue(self):
        [app.update(status=mkt.STATUS_NULL) for app in self.apps]
        if self.uses_es():
            self.reindex(Webapp)
        req = req_factory_factory(
            self.url,
            user=UserProfile.objects.get(email='editor@mozilla.com'))
        doc = pq(queue_apps(req).content)
        assert not doc('#addon-queue tbody tr').length

    def test_waiting_time(self):
        """Check objects show queue objects' created."""
        res = self.client.get(self.url)
        waiting_times = [wait.attrib['isotime'] for wait in
                         pq(res.content)('td time')]
        expected_waiting_times = [isotime(app.latest_version.nomination)
                                  for app in self.apps[0:2]]
        self.assertSetEqual(expected_waiting_times, waiting_times)


class TestAppQueueES(mkt.site.tests.ESTestCase, TestAppQueue):

    def setUp(self):
        super(TestAppQueueES, self).setUp()
        self.create_switch('reviewer-tools-elasticsearch')
        self.reindex(Webapp)


class TestRegionQueue(AppReviewerTest, AccessMixin, FlagsMixin, SearchMixin,
                      XSSMixin):

    def setUp(self):
        super(TestRegionQueue, self).setUp()
        self.apps = [app_factory(name='WWW',
                                 status=mkt.STATUS_PUBLIC),
                     app_factory(name='XXX',
                                 status=mkt.STATUS_APPROVED),
                     app_factory(name='YYY',
                                 status=mkt.STATUS_PUBLIC),
                     app_factory(name='ZZZ',
                                 status=mkt.STATUS_PENDING)]
        # WWW and XXX are the only ones actually requested to be public.
        self.apps[0].geodata.update(region_cn_status=mkt.STATUS_PENDING,
                                    region_cn_nominated=self.days_ago(2))
        self.apps[1].geodata.update(region_cn_status=mkt.STATUS_PENDING,
                                    region_cn_nominated=self.days_ago(1))
        self.apps[2].geodata.update(region_cn_status=mkt.STATUS_PUBLIC)

        self.grant_permission(self.reviewer_user, 'Apps:ReviewRegionCN')
        self.login_as_editor()
        self.url = reverse('reviewers.apps.queue_region',
                           args=[mkt.regions.CHN.slug])

    def test_template_links(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        links = pq(r.content)('.regional-queue tbody tr td:first-child a')
        apps = Webapp.objects.pending_in_region('cn').order_by(
            '_geodata__region_cn_nominated')
        src = '?src=queue-region-cn'
        expected = [
            (unicode(apps[0].name), apps[0].get_url_path() + src),
            (unicode(apps[1].name), apps[1].get_url_path() + src),
        ]
        check_links(expected, links, verify=False)

    def test_escalated_not_in_queue(self):
        self.grant_permission(self.snr_reviewer_user, 'Apps:ReviewRegionCN')
        self.login_as_senior_reviewer()
        self.apps[0].escalationqueue_set.create()
        res = self.client.get(self.url)
        eq_([a.app for a in res.context['addons']], [self.apps[1]])


@mock.patch('mkt.versions.models.Version.is_privileged', False)
class TestRereviewQueue(AppReviewerTest, AccessMixin, FlagsMixin, SearchMixin,
                        XSSMixin):

    def setUp(self):
        super(TestRereviewQueue, self).setUp()
        self.apps = [app_factory(name='XXX'),
                     app_factory(name='YYY'),
                     app_factory(name='ZZZ')]
        RereviewQueue.objects.create(addon=self.apps[0]).update(
            created=self.days_ago(5))
        RereviewQueue.objects.create(addon=self.apps[1]).update(
            created=self.days_ago(3))
        RereviewQueue.objects.create(addon=self.apps[2]).update(
            created=self.days_ago(1))
        self.apps[0].update(created=self.days_ago(15))
        self.apps[1].update(created=self.days_ago(13))
        self.apps[2].update(created=self.days_ago(11))

        if self.uses_es():
            self.reindex(Webapp)

        self.url = reverse('reviewers.apps.queue_rereview')

    def tearDown(self):
        if self.uses_es():
            unindex_webapps([app.id for app in self.apps])
        super(TestRereviewQueue, self).tearDown()

    def review_url(self, app):
        return reverse('reviewers.apps.review', args=[app.app_slug])

    def test_template_links(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        links = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(2) a')
        apps = [rq.addon for rq in
                RereviewQueue.objects.all().order_by('created')]
        expected = [
            (unicode(apps[0].name), self.review_url(apps[0])),
            (unicode(apps[1].name), self.review_url(apps[1])),
            (unicode(apps[2].name), self.review_url(apps[2])),
        ]
        check_links(expected, links, verify=False)

    def test_waiting_time(self):
        """Check objects show queue objects' created."""
        r = self.client.get(self.url)
        waiting_times = [wait.attrib['isotime'] for wait in
                         pq(r.content)('td time')]
        expected_waiting_times = [
            isotime(app.rereviewqueue_set.all()[0].created)
            for app in self.apps]
        self.assertSetEqual(expected_waiting_times, waiting_times)

    def test_action_buttons_public_senior_reviewer(self):
        self.login_as_senior_reviewer()

        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Reject', 'reject'),
            (u'Ban app', 'disable'),
            (u'Clear Re-review', 'clear_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_public(self):
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Reject', 'reject'),
            (u'Clear Re-review', 'clear_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_reject(self):
        self.apps[0].update(status=mkt.STATUS_REJECTED)
        self.apps[0].latest_version.files.update(status=mkt.STATUS_DISABLED)
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Clear Re-review', 'clear_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_invalid_page(self):
        r = self.client.get(self.url, {'page': 999})
        eq_(r.status_code, 200)
        eq_(r.context['pager'].number, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (3)')
        eq_(links[2].text, u'Updates (0)')

    def test_queue_count_senior_reviewer(self):
        self.login_as_senior_reviewer()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (3)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Escalations (0)')

    def test_escalated_not_in_queue(self):
        self.login_as_senior_reviewer()
        EscalationQueue.objects.create(addon=self.apps[0])
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        if self.uses_es():
            self.assertSetEqual([a.id for a in res.context['addons']],
                                [a.id for a in self.apps[1:]])
        else:
            self.assertSetEqual([a.app for a in res.context['addons']],
                                self.apps[1:])

        doc = pq(res.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (2)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Escalations (1)')

    def test_addon_deleted(self):
        app = self.apps[0]
        app.delete()
        eq_(RereviewQueue.objects.filter(addon=app).exists(), False)


class TestRereviewQueueES(mkt.site.tests.ESTestCase, TestRereviewQueue):

    def setUp(self):
        super(TestRereviewQueueES, self).setUp()
        self.create_switch('reviewer-tools-elasticsearch')
        self.reindex(Webapp)


@mock.patch('mkt.versions.models.Version.is_privileged', False)
class TestUpdateQueue(AppReviewerTest, AccessMixin, FlagsMixin, SearchMixin,
                      XSSMixin):

    def setUp(self):
        super(TestUpdateQueue, self).setUp()
        app1 = app_factory(is_packaged=True, name='XXX',
                           version_kw={'version': '1.0',
                                       'created': self.days_ago(2),
                                       'nomination': self.days_ago(2)})
        app2 = app_factory(is_packaged=True, name='YYY',
                           version_kw={'version': '1.0',
                                       'created': self.days_ago(2),
                                       'nomination': self.days_ago(2)})

        version_factory(addon=app1, version='1.1', created=self.days_ago(1),
                        nomination=self.days_ago(1),
                        file_kw={'status': mkt.STATUS_PENDING})
        version_factory(addon=app2, version='1.1', created=self.days_ago(1),
                        nomination=self.days_ago(1),
                        file_kw={'status': mkt.STATUS_PENDING})

        self.apps = list(Webapp.objects.order_by('id'))
        self.url = reverse('reviewers.apps.queue_updates')

    def tearDown(self):
        if self.uses_es():
            unindex_webapps([app.id for app in self.apps])
        super(TestUpdateQueue, self).tearDown()

    def review_url(self, app):
        return reverse('reviewers.apps.review', args=[app.app_slug])

    def test_template_links(self):
        self.apps[0].versions.latest().update(nomination=self.days_ago(2))
        self.apps[1].versions.latest().update(nomination=self.days_ago(1))
        if self.uses_es():
            self.reindex(Webapp)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        links = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(2) a')
        expected = [
            (unicode(self.apps[0].name), self.review_url(self.apps[0])),
            (unicode(self.apps[1].name), self.review_url(self.apps[1])),
        ]
        check_links(expected, links, verify=False)

    def test_action_buttons_public_senior_reviewer(self):
        self.apps[0].versions.latest().files.update(status=mkt.STATUS_PUBLIC)
        self.login_as_senior_reviewer()

        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Reject', 'reject'),
            (u'Ban app', 'disable'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_public(self):
        self.apps[0].versions.latest().files.update(status=mkt.STATUS_PUBLIC)

        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Reject', 'reject'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_reject(self):
        self.apps[0].versions.latest().files.update(status=mkt.STATUS_DISABLED)

        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Escalate', 'escalate'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_invalid_page(self):
        r = self.client.get(self.url, {'page': 999})
        eq_(r.status_code, 200)
        eq_(r.context['pager'].number, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (2)')

    def test_queue_count_senior_reviewer(self):
        self.login_as_senior_reviewer()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (2)')
        eq_(links[3].text, u'Escalations (0)')

    def test_escalated_not_in_queue(self):
        self.login_as_senior_reviewer()
        EscalationQueue.objects.create(addon=self.apps[0])
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        eq_([a.app.id for a in res.context['addons']],
            [app.id for app in self.apps[1:]])

        doc = pq(res.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (1)')
        eq_(links[3].text, u'Escalations (1)')

    def test_order(self):
        self.apps[0].update(created=self.days_ago(10))
        self.apps[1].update(created=self.days_ago(5))
        self.apps[0].versions.latest().update(nomination=self.days_ago(1))
        self.apps[1].versions.latest().update(nomination=self.days_ago(4))
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        apps = list(res.context['addons'])
        eq_(apps[0].app.id, self.apps[1].id)
        eq_(apps[1].app.id, self.apps[0].id)

    def test_only_updates_in_queue(self):
        # Add new packaged app, which should only show up in the pending queue.
        app = app_factory(is_packaged=True, name='ZZZ',
                          status=mkt.STATUS_PENDING,
                          version_kw={'version': '1.0'},
                          file_kw={'status': mkt.STATUS_PENDING})
        self.apps.append(app)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        apps = [a.app for a in res.context['addons']]
        assert app not in apps, (
            'Unexpected: Found a new packaged app in the updates queue.')
        eq_(pq(res.content)('.tabnav li a')[2].text, u'Updates (2)')

    def test_approved_update_in_queue(self):
        app = app_factory(is_packaged=True, name='YYY',
                          status=mkt.STATUS_APPROVED,
                          version_kw={'version': '1.0',
                                      'created': self.days_ago(2),
                                      'nomination': self.days_ago(2)})
        self.apps.append(app)
        File.objects.filter(version__addon=app).update(status=app.status)

        version_factory(addon=app, version='1.1', created=self.days_ago(1),
                        nomination=self.days_ago(1),
                        file_kw={'status': mkt.STATUS_PENDING})

        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        assert app.id in [a.app.id for a in res.context['addons']]
        eq_(pq(res.content)('.tabnav li a')[2].text, u'Updates (3)')

    def test_update_queue_with_empty_nomination(self):
        app = app_factory(is_packaged=True, name='YYY',
                          status=mkt.STATUS_NULL,
                          version_kw={'version': '1.0',
                                      'created': self.days_ago(2),
                                      'nomination': None})
        self.apps.append(app)
        first_version = app.latest_version
        version_factory(addon=app, version='1.1', created=self.days_ago(1),
                        nomination=None,
                        file_kw={'status': mkt.STATUS_PENDING})

        # Now that we have a version with nomination=None, reset app status.
        app.update(status=mkt.STATUS_APPROVED)
        File.objects.filter(version=first_version).update(status=app.status)

        # Safeguard: we /really/ want to test with nomination=None.
        eq_(app.latest_version.reload().nomination, None)

        if self.uses_es():
            self.reindex(Webapp)

        res = self.client.get(self.url)
        assert app.id in [a.app.id for a in res.context['addons']]
        eq_(pq(res.content)('.tabnav li a')[2].text, u'Updates (3)')

    def test_deleted_version_not_in_queue(self):
        """
        This tests that an app with a prior pending version that got
        deleted doesn't trigger the app to remain in the review queue.
        """
        app = self.apps[0]
        # File is PENDING and delete current version.
        old_ver = app.versions.order_by('id')[0]
        old_ver.files.latest().update(status=mkt.STATUS_PENDING)
        old_ver.delete()
        # "Approve" the app.
        app.versions.latest().files.latest().update(status=mkt.STATUS_PUBLIC)
        eq_(app.reload().status, mkt.STATUS_PUBLIC)
        if self.uses_es():
            self.reindex(Webapp)

        res = self.client.get(self.url)
        eq_(res.status_code, 200)

        # Verify that our app has 2 versions.
        eq_(Version.with_deleted.filter(addon=app).count(), 2)

        # Verify the apps in the context are what we expect.
        doc = pq(res.content)
        eq_(doc('.tabnav li a')[2].text, u'Updates (1)')
        apps = [a.app.id for a in res.context['addons']]
        ok_(app.id not in apps)
        ok_(self.apps[1].id in apps)

    def test_waiting_time(self):
        """Check objects show queue objects' created."""
        r = self.client.get(self.url)
        waiting_times = [wait.attrib['isotime'] for wait in
                         pq(r.content)('td time')]
        expected_waiting_times = [isotime(app.latest_version.nomination)
                                  for app in self.apps]
        self.assertSetEqual(expected_waiting_times, waiting_times)


class TestUpdateQueueES(mkt.site.tests.ESTestCase, TestUpdateQueue):

    def setUp(self):
        super(TestUpdateQueueES, self).setUp()
        self.create_switch('reviewer-tools-elasticsearch')
        self.reindex(Webapp)


@mock.patch('mkt.versions.models.Version.is_privileged', False)
class TestEscalationQueue(AppReviewerTest, AccessMixin, FlagsMixin,
                          SearchMixin, XSSMixin):

    def setUp(self):
        super(TestEscalationQueue, self).setUp()
        self.apps = [app_factory(name='XXX'),
                     app_factory(name='YYY'),
                     app_factory(name='ZZZ')]

        EscalationQueue.objects.create(addon=self.apps[0]).update(
            created=self.days_ago(5))
        EscalationQueue.objects.create(addon=self.apps[1]).update(
            created=self.days_ago(3))
        EscalationQueue.objects.create(addon=self.apps[2]).update(
            created=self.days_ago(1))
        self.apps[0].update(created=self.days_ago(15))
        self.apps[1].update(created=self.days_ago(13))
        self.apps[2].update(created=self.days_ago(11))

        self.login_as_senior_reviewer()
        self.url = reverse('reviewers.apps.queue_escalated')

    def tearDown(self):
        if self.uses_es():
            unindex_webapps([app.id for app in self.apps])
        super(TestEscalationQueue, self).tearDown()

    def review_url(self, app):
        return reverse('reviewers.apps.review', args=[app.app_slug])

    def test_flag_blocked(self):
        # Blocklisted apps should only be in the update queue, so this flag
        # check is here rather than in FlagsMixin.
        self.apps[0].update(status=mkt.STATUS_BLOCKED)
        if self.uses_es():
            self.reindex(Webapp)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tds = pq(res.content)('#addon-queue tbody tr td.flags')
        flags = tds('div.sprite-reviewer-blocked')
        eq_(flags.length, 1)

    def test_no_access_regular_reviewer(self):
        self.login_as_editor()
        res = self.client.get(self.url)
        eq_(res.status_code, 403)

    def test_template_links(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        links = pq(r.content)('#addon-queue tbody')('tr td:nth-of-type(2) a')
        apps = [rq.addon for rq in
                EscalationQueue.objects.all().order_by('addon__created')]
        expected = [
            (unicode(apps[0].name), self.review_url(apps[0])),
            (unicode(apps[1].name), self.review_url(apps[1])),
            (unicode(apps[2].name), self.review_url(apps[2])),
        ]
        check_links(expected, links, verify=False)

    def test_waiting_time(self):
        """Check objects show queue objects' created."""
        r = self.client.get(self.url)
        waiting_times = [wait.attrib['isotime'] for wait in
                         pq(r.content)('td time')]
        expected_waiting_times = [
            isotime(app.escalationqueue_set.all()[0].created)
            for app in self.apps]
        self.assertSetEqual(expected_waiting_times, waiting_times)

    def test_action_buttons_public(self):
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Reject', 'reject'),
            (u'Ban app', 'disable'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Clear Escalation', 'clear_escalation'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_action_buttons_reject(self):
        self.apps[0].update(status=mkt.STATUS_REJECTED)
        self.apps[0].latest_version.files.update(status=mkt.STATUS_DISABLED)
        r = self.client.get(self.review_url(self.apps[0]))
        eq_(r.status_code, 200)
        actions = pq(r.content)('#review-actions input')
        expected = [
            (u'Approve', 'public'),
            (u'Ban app', 'disable'),
            (u'Request Re-review', 'manual_rereview'),
            (u'Clear Escalation', 'clear_escalation'),
            (u'Message developer', 'info'),
            (u'Private comment', 'comment'),
        ]
        self.check_actions(expected, actions)

    def test_invalid_page(self):
        r = self.client.get(self.url, {'page': 999})
        eq_(r.status_code, 200)
        eq_(r.context['pager'].number, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Escalations (3)')

    def test_addon_deleted(self):
        app = self.apps[0]
        app.delete()
        eq_(EscalationQueue.objects.filter(addon=app).exists(), False)


class TestEscalationQueueES(mkt.site.tests.ESTestCase, TestEscalationQueue):

    def setUp(self):
        super(TestEscalationQueueES, self).setUp()
        self.create_switch('reviewer-tools-elasticsearch')
        self.reindex(Webapp)


class TestReviewTransaction(AttachmentManagementMixin,
                            mkt.site.tests.MockEsMixin,
                            mkt.site.tests.MockBrowserIdMixin,
                            test.TransactionTestCase,
                            TestedonManagementMixin):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestReviewTransaction, self).setUp()
        mkt.site.tests.TestCase.grant_permission(
            user_factory(email='editor'), 'Apps:Review')
        self.mock_browser_id()

    def get_app(self):
        return Webapp.objects.get(id=337141)

    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    @mock.patch('lib.crypto.packaged.sign_app')
    def test_public_sign(self, sign_mock, json_mock, update_cached_manifests):
        self.app = self.get_app()
        self.version = self.app.latest_version
        self.version.files.all().update(status=mkt.STATUS_PENDING)

        with private_storage.open(
                self.version.files.all()[0].file_path, 'w') as f:
            f.write('.')
        public_storage.delete(self.version.files.all()[0].file_path)
        self.app.update(status=mkt.STATUS_PENDING, is_packaged=True,
                        _current_version=None, _signal=False)
        eq_(self.get_app().status, mkt.STATUS_PENDING)

        update_cached_manifests.reset_mock()
        sign_mock.return_value = None  # Didn't fail.
        json_mock.return_value = {'name': 'Something'}

        self.login('editor@mozilla.com')
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        resp = self.client.post(
            reverse('reviewers.apps.review', args=[self.app.app_slug]), data)
        eq_(resp.status_code, 302)

        eq_(self.get_app().status, mkt.STATUS_PUBLIC)
        eq_(update_cached_manifests.delay.call_count, 1)

    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.get_manifest_json')
    @mock.patch('lib.crypto.packaged.sign')
    def test_public_sign_failure(self, sign_mock, json_mock,
                                 update_cached_manifests):
        self.app = self.get_app()
        self.version = self.app.latest_version
        self.version.files.all().update(status=mkt.STATUS_PENDING)
        self.app.update(status=mkt.STATUS_PENDING, is_packaged=True,
                        _current_version=None, _signal=False)
        eq_(self.get_app().status, mkt.STATUS_PENDING)

        sign_mock.side_effect = packaged.SigningError
        json_mock.return_value = {'name': 'Something'}

        self.login('editor@mozilla.com')
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        resp = self.client.post(
            reverse('reviewers.apps.review', args=[self.app.app_slug]), data)
        eq_(resp.status_code, 302)

        eq_(self.get_app().status, mkt.STATUS_PENDING)
        eq_(update_cached_manifests.delay.call_count, 0)


class TestReviewMixin(object):
    # E.g commreply+12e0caffc4ca4174a6f62300c0ff180a@marketplace.firefox.com .
    COMM_REPLY_RE = r'^commreply\+[a-f0-9]+\@marketplace\.firefox\.com$'

    def post(self, data, queue='pending'):
        res = self.client.post(self.url, data)
        self.assert3xx(res, reverse('reviewers.apps.queue_%s' % queue))

    def _check_email(self, msg, subject, to=None):
        if to:
            eq_(msg.to, to)
        else:
            eq_(msg.to, list(self.app.authors.values_list('email', flat=True)))
        assert re.match(self.COMM_REPLY_RE, msg.extra_headers['Reply-To'])

        eq_(msg.cc, [])
        eq_(msg.from_email, settings.MKT_REVIEWERS_EMAIL)

        if subject:
            eq_(msg.subject, '%s: %s' % (subject, self.app.name))

    def _get_mail(self, email):
        return filter(lambda x: x.to[0].startswith(email), mail.outbox)[0]

    def _check_email_dev_and_contact(self, subject, outbox_len=2):
        """
        Helper for checking developer and Mozilla contact get emailed.
        """
        eq_(len(mail.outbox), outbox_len)
        # Developer.
        self._check_email(self._get_mail('steamcube'), subject)
        # Mozilla contact.
        self._check_email(self._get_mail('contact'), subject,
                          to=[self.mozilla_contact])

    def _check_thread(self):
        thread = self.app.threads
        eq_(thread.count(), 1)

        thread = thread.get()
        perms = ('developer', 'reviewer', 'staff')

        for key in perms:
            assert getattr(thread, 'read_permission_%s' % key)

    def _check_email_body(self, msg=None):
        if not msg:
            msg = mail.outbox[0]
        body = msg.message().as_string()
        url = self.app.get_url_path()
        assert url in body, 'Could not find apps detail URL in %s' % msg

    def _check_log(self, action):
        assert AppLog.objects.filter(
            addon=self.app, activity_log__action=action.id).exists(), (
                "Didn't find `%s` action in logs." % action.short)

    def _check_score(self, reviewed_type):
        scores = ReviewerScore.objects.all()
        assert len(scores) > 0
        eq_(scores[0].score, mkt.REVIEWED_SCORES[reviewed_type])
        eq_(scores[0].note_key, reviewed_type)


class TestReviewApp(SetupFilesMixin, AppReviewerTest, TestReviewMixin,
                    AccessMixin, AttachmentManagementMixin,
                    TestedonManagementMixin):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestReviewApp, self).setUp()
        self.mozilla_contact = 'contact@mozilla.com'
        self.app = self.get_app()
        self.app = make_game(self.app, True)
        self.app.update(status=mkt.STATUS_PENDING,
                        mozilla_contact=self.mozilla_contact)
        self.version = self.app.latest_version
        self.version.files.all().update(status=mkt.STATUS_PENDING)
        self.file = self.version.all_files[0]
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])
        self.setup_files()

    def get_app(self):
        return Webapp.objects.get(id=337141)

    def test_review_viewing_ping(self):
        eq_(self.client.post(reverse('reviewers.review_viewing')).status_code,
            200)

    @mock.patch('mkt.webapps.models.Webapp.in_rereview_queue')
    def test_rereview(self, is_rereview_queue):
        is_rereview_queue.return_value = True
        content = pq(self.client.get(self.url).content)
        assert content('#queue-rereview').length

    @mock.patch('mkt.webapps.models.Webapp.in_escalation_queue')
    def test_escalated(self, in_escalation_queue):
        in_escalation_queue.return_value = True
        content = pq(self.client.get(self.url).content)
        assert content('#queue-escalation').length

    def test_cannot_review_my_app(self):
        with self.settings(ALLOW_SELF_REVIEWS=False):
            self.app.addonuser_set.create(
                user=UserProfile.objects.get(email='editor@mozilla.com'))
            res = self.client.head(self.url)
            self.assert3xx(res, reverse('reviewers.home'))
            res = self.client.post(self.url)
            self.assert3xx(res, reverse('reviewers.home'))

    def test_cannot_review_blocklisted_app(self):
        self.app.update(status=mkt.STATUS_BLOCKED)
        res = self.client.get(self.url)
        self.assert3xx(res, reverse('reviewers.home'))
        res = self.client.post(self.url)
        self.assert3xx(res, reverse('reviewers.home'))

    def test_review_no_latest_version(self):
        self.app.versions.all().delete()
        self.app.reload()
        eq_(self.app.latest_version, None)
        eq_(self.app.current_version, None)
        response = self.client.get(self.url)
        eq_(response.status_code, 200)
        doc = pq(response.content)
        assert not doc('input[name=action][value=info]').length
        assert not doc('input[name=action][value=comment]').length
        assert not doc('input[name=action][value=public]').length
        assert not doc('input[name=action][value=reject]').length

        # Also try with a packaged app.
        self.app.update(is_packaged=True)
        response = self.client.get(self.url)
        eq_(response.status_code, 200)

    def test_sr_can_review_blocklisted_app(self):
        self.app.update(status=mkt.STATUS_BLOCKED)
        self.login_as_senior_reviewer()
        eq_(self.client.get(self.url).status_code, 200)
        data = {'action': 'public', 'comments': 'yo'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        res = self.client.post(self.url, data)
        self.assert3xx(res, reverse('reviewers.apps.queue_pending'))

    def test_pending_to_reject_w_device_overrides(self):
        # This shouldn't be possible unless there's form hacking.
        AddonDeviceType.objects.create(addon=self.app,
                                       device_type=mkt.DEVICE_DESKTOP.id)
        AddonDeviceType.objects.create(addon=self.app,
                                       device_type=mkt.DEVICE_TABLET.id)
        eq_(self.app.publish_type, mkt.PUBLISH_IMMEDIATE)
        data = {'action': 'reject', 'comments': 'something',
                'device_override': [mkt.DEVICE_DESKTOP.id]}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.publish_type, mkt.PUBLISH_IMMEDIATE)
        eq_(app.status, mkt.STATUS_REJECTED)
        eq_(set([o.id for o in app.device_types]),
            set([mkt.DEVICE_DESKTOP.id, mkt.DEVICE_TABLET.id]))

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_pending_to_public_w_requirements_overrides(self, storefront_mock):
        data = {'action': 'public', 'comments': 'something',
                'has_sms': True}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        assert not self.app.latest_version.features.has_sms
        self.post(data)
        app = self.get_app()
        assert app.latest_version.features.has_sms
        eq_(app.publish_type, mkt.PUBLISH_PRIVATE)
        eq_(app.status, mkt.STATUS_APPROVED)
        self._check_log(mkt.LOG.REVIEW_FEATURES_OVERRIDE)

        # A reviewer changing features shouldn't generate a re-review.
        eq_(RereviewQueue.objects.count(), 0)

        assert not storefront_mock.called

    def test_pending_to_reject_w_requirements_overrides(self):
        # Rejecting an app doesn't let you override features requirements.
        data = {'action': 'reject', 'comments': 'something',
                'has_sms': True}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        assert not self.app.latest_version.features.has_sms
        self.post(data)
        app = self.get_app()
        assert not app.latest_version.features.has_sms
        eq_(app.publish_type, mkt.PUBLISH_IMMEDIATE)
        eq_(app.status, mkt.STATUS_REJECTED)

    def test_pending_to_reject_w_requirements_overrides_nothing_changed(self):
        self.version.features.update(has_sms=True)
        data = {'action': 'public', 'comments': 'something',
                'has_sms': True}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        assert self.app.latest_version.features.has_sms
        self.post(data)
        app = self.get_app()
        assert app.latest_version.features.has_sms
        eq_(app.publish_type, mkt.PUBLISH_IMMEDIATE)
        eq_(app.status, mkt.STATUS_PUBLIC)
        action_id = mkt.LOG.REVIEW_FEATURES_OVERRIDE.id
        assert not AppLog.objects.filter(
            addon=self.app, activity_log__action=action_id).exists()

    @mock.patch('mkt.reviewers.views.messages.success', new=mock.Mock)
    def test_incomplete_cant_approve(self):
        self.app.update(status=mkt.STATUS_NULL)
        self.app.latest_version.files.update(status=mkt.STATUS_NULL)
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)

        # Still incomplete.
        eq_(self.get_app().status, mkt.STATUS_NULL)

    def test_notification_email_translation(self):
        # https://bugzilla.mozilla.org/show_bug.cgi?id=1127790
        raise SkipTest
        """Test that the app name is translated with the app's default_locale
        and not the reviewer's when we are sending notification emails."""
        original_name = unicode(self.app.name)
        fr_translation = u'Mais allô quoi!'
        es_translation = u'¿Dónde está la biblioteca?'
        self.app.name = {
            'fr': fr_translation,
            'es': es_translation,
        }
        self.app.default_locale = 'fr'
        self.app.save()

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.client.post(self.url, data, HTTP_ACCEPT_LANGUAGE='es')
        eq_(translation.get_language(), 'es')

        eq_(len(mail.outbox), 2)
        msg = mail.outbox[0]

        assert original_name not in msg.subject
        assert es_translation not in msg.subject
        assert fr_translation in msg.subject
        assert original_name not in msg.body
        assert es_translation not in msg.body
        assert fr_translation in msg.body

    @mock.patch('lib.crypto.packaged.sign')
    def test_require_sig_for_public(self, sign):
        sign.side_effect = packaged.SigningError
        self.get_app().update(is_packaged=True)
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.client.post(self.url, data)
        eq_(self.get_app().status, mkt.STATUS_PENDING)

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_pending_to_public_no_mozilla_contact(self, storefront_mock):
        self.app.update(mozilla_contact='')
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        eq_(app.current_version.files.all()[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], ('Approved'))
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)

        assert storefront_mock.called

    @mock.patch('mkt.reviewers.views.messages.success')
    def test_pending_to_escalation(self, messages):
        data = {'action': 'escalate', 'comments': 'soup her man'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(EscalationQueue.objects.count(), 1)
        self._check_log(mkt.LOG.ESCALATE_MANUAL)

        # Test 2 emails: 1 to dev, 1 to admin.
        eq_(len(mail.outbox), 2)
        self._check_email(self._get_mail('steamcube'), 'Escalated')
        self._check_email(
            self._get_mail('snrreviewer'), 'Escalated',
            to=[self.snr_reviewer_user.email])

        eq_(messages.call_args_list[0][0][1], 'Review successfully processed.')

    def test_pending_to_disable_senior_reviewer(self):
        self.login_as_senior_reviewer()

        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'banned ur app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_DISABLED)
        eq_(app.latest_version.files.all()[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.APP_DISABLED)
        self._check_email_dev_and_contact('Banned')

    def test_pending_to_disable(self):
        # Only senior reviewers can ban apps.
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'banned ur app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        res = self.client.post(self.url, data)
        eq_(res.status_code, 200)
        ok_('action' in res.context['form'].errors)
        eq_(self.get_app().status, mkt.STATUS_PUBLIC)
        eq_(len(mail.outbox), 0)

    @mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
    def test_escalation_to_public(self, storefront_mock):
        EscalationQueue.objects.create(addon=self.app)
        eq_(self.app.status, mkt.STATUS_PENDING)
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='escalated')
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        eq_(app.current_version.files.all()[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)
        eq_(EscalationQueue.objects.count(), 0)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()

        assert storefront_mock.called

    def test_escalation_to_reject(self):
        EscalationQueue.objects.create(addon=self.app)
        eq_(self.app.status, mkt.STATUS_PENDING)
        files = list(self.version.files.values_list('id', flat=True))
        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='escalated')
        app = self.get_app()
        eq_(app.status, mkt.STATUS_REJECTED)
        eq_(File.objects.filter(id__in=files)[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.REJECT_VERSION)
        eq_(EscalationQueue.objects.count(), 0)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)

    def test_escalation_to_disable_senior_reviewer(self):
        self.login_as_senior_reviewer()
        EscalationQueue.objects.create(addon=self.app)
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'banned ur app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='escalated')
        app = self.get_app()
        eq_(app.status, mkt.STATUS_DISABLED)
        eq_(app.latest_version.files.all()[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.APP_DISABLED)
        eq_(EscalationQueue.objects.count(), 0)
        self._check_email_dev_and_contact('Banned')

    def test_escalation_to_disable(self):
        EscalationQueue.objects.create(addon=self.app)
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'banned ur app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        res = self.client.post(self.url, data, queue='escalated')
        eq_(res.status_code, 200)
        ok_('action' in res.context['form'].errors)
        eq_(self.get_app().status, mkt.STATUS_PUBLIC)
        eq_(EscalationQueue.objects.count(), 1)
        eq_(len(mail.outbox), 0)

    def test_clear_escalation(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        EscalationQueue.objects.create(addon=self.app)
        data = {'action': 'clear_escalation', 'comments': 'all clear'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='escalated')
        eq_(EscalationQueue.objects.count(), 0)
        self._check_log(mkt.LOG.ESCALATION_CLEARED)
        # Ensure we don't send email to developer on clearing escalations.
        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], None, to=[self.mozilla_contact])

    def test_rereview_to_reject(self):
        RereviewQueue.objects.create(addon=self.app)
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='rereview')
        eq_(self.get_app().status, mkt.STATUS_REJECTED)
        self._check_log(mkt.LOG.REJECT_VERSION)
        eq_(RereviewQueue.objects.count(), 0)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_REREVIEW)

    def test_rereview_to_disable_senior_reviewer(self):
        self.login_as_senior_reviewer()

        RereviewQueue.objects.create(addon=self.app)
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='rereview')
        eq_(self.get_app().status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.APP_DISABLED)
        eq_(RereviewQueue.objects.filter(addon=self.app).count(), 0)
        self._check_email_dev_and_contact('Banned')

    def test_rereview_to_disable(self):
        RereviewQueue.objects.create(addon=self.app)
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'disable', 'comments': 'banned ur app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        res = self.client.post(self.url, data, queue='rereview')
        eq_(res.status_code, 200)
        ok_('action' in res.context['form'].errors)
        eq_(self.get_app().status, mkt.STATUS_PUBLIC)
        eq_(RereviewQueue.objects.filter(addon=self.app).count(), 1)
        eq_(len(mail.outbox), 0)

    def test_manual_rereview(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        data = {'action': 'manual_rereview', 'comments': 'man dem'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        # The app status shouldn't change.
        eq_(self.get_app().status, mkt.STATUS_PUBLIC)
        eq_(RereviewQueue.objects.count(), 1)
        self._check_log(mkt.LOG.REREVIEW_MANUAL)

        # Ensure we don't send email to developer on manual rereviews.
        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], None, to=[self.mozilla_contact])

    def test_clear_rereview(self):
        self.app.update(status=mkt.STATUS_PUBLIC)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        RereviewQueue.objects.create(addon=self.app)
        data = {'action': 'clear_rereview', 'comments': 'all clear'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='rereview')
        eq_(RereviewQueue.objects.count(), 0)
        self._check_log(mkt.LOG.REREVIEW_CLEARED)
        # Ensure we don't send emails to the developer on clearing re-reviews.
        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], None, to=[self.mozilla_contact])
        self._check_score(mkt.REVIEWED_WEBAPP_REREVIEW)

    def test_clear_rereview_unlisted(self):
        self.app.update(status=mkt.STATUS_UNLISTED)
        self.app.latest_version.files.update(status=mkt.STATUS_PUBLIC)
        RereviewQueue.objects.create(addon=self.app)
        data = {'action': 'clear_rereview', 'comments': 'all clear'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='rereview')
        eq_(RereviewQueue.objects.count(), 0)
        self._check_log(mkt.LOG.REREVIEW_CLEARED)
        # Ensure we don't send emails to the developer on clearing re-reviews.
        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], None, to=[self.mozilla_contact])
        self._check_score(mkt.REVIEWED_WEBAPP_REREVIEW)

    def test_rereview_to_escalation(self):
        RereviewQueue.objects.create(addon=self.app)
        data = {'action': 'escalate', 'comments': 'soup her man'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data, queue='rereview')
        eq_(EscalationQueue.objects.count(), 1)
        self._check_log(mkt.LOG.ESCALATE_MANUAL)
        # Test 2 emails: 1 to dev, 1 to admin.
        eq_(len(mail.outbox), 2)
        self._check_email(self._get_mail('steamcube'), 'Escalated')
        self._check_email(
            self._get_mail('snrreviewer'), 'Escalated',
            to=[self.snr_reviewer_user.email])

    def test_more_information(self):
        # Test the same for all queues.
        data = {'action': 'info', 'comments': 'Knead moor in faux'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(self.get_app().status, mkt.STATUS_PENDING)
        self._check_log(mkt.LOG.REQUEST_INFORMATION)
        vqs = self.get_app().versions.all()
        eq_(vqs.count(), 1)
        eq_(vqs.filter(has_info_request=True).count(), 1)
        self._check_email_dev_and_contact('Reviewer comment')

    def test_multi_cc_email(self):
        # Test multiple mozilla_contact emails via more information.
        contacts = [user_factory(email=u'á').email,
                    user_factory(email=u'ç').email]
        self.mozilla_contact = ', '.join(contacts)
        self.app.update(mozilla_contact=self.mozilla_contact)
        data = {'action': 'info', 'comments': 'Knead moor in faux'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(len(mail.outbox), 3)
        subject = 'Reviewer comment'
        self._check_email(self._get_mail('steamcube'), subject)
        self._check_email(self._get_mail(contacts[0]), subject,
                          to=[contacts[0]])
        self._check_email(self._get_mail(contacts[1]), subject,
                          to=[contacts[1]])

    def test_comment(self):
        # Test the same for all queues.
        data = {'action': 'comment', 'comments': 'mmm, nice app'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(len(mail.outbox), 1)
        self._check_email(mail.outbox[0], None, to=[self.mozilla_contact])
        self._check_log(mkt.LOG.COMMENT_VERSION)

    def test_receipt_no_node(self):
        res = self.client.get(self.url)
        eq_(len(pq(res.content)('#receipt-check-result')), 0)

    def test_receipt_has_node(self):
        self.get_app().update(premium_type=mkt.ADDON_PREMIUM)
        res = self.client.get(self.url)
        eq_(len(pq(res.content)('.reviewers-desktop #receipt-check-result')),
            1)
        eq_(len(pq(res.content)('.reviewers-mobile #receipt-check-result')),
            1)

    @mock.patch('mkt.reviewers.views.requests.get')
    def test_manifest_json(self, mock_get):
        m = mock.Mock()
        m.content = 'the manifest contents <script>'
        m.headers = CaseInsensitiveDict(
            {'content-type': 'application/x-web-app-manifest+json <script>'})
        mock_get.return_value = m

        expected = {
            'content': 'the manifest contents &lt;script&gt;',
            'headers': {'content-type':
                        'application/x-web-app-manifest+json &lt;script&gt;'},
            'success': True,
            'permissions': {}
        }

        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        eq_(json.loads(r.content), expected)

    @mock.patch('mkt.reviewers.views.requests.get')
    def test_manifest_json_unicode(self, mock_get):
        m = mock.Mock()
        m.content = u'كك some foreign ish'
        m.headers = CaseInsensitiveDict({})
        mock_get.return_value = m

        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        eq_(json.loads(r.content), {'content': u'كك some foreign ish',
                                    'headers': {}, 'success': True,
                                    'permissions': {}})

    @mock.patch('mkt.reviewers.views.requests.get')
    def test_manifest_json_encoding(self, mock_get):
        m = mock.Mock()
        m.content = open(self.manifest_path('non-utf8.webapp')).read()
        m.headers = CaseInsensitiveDict({})
        mock_get.return_value = m

        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        data = json.loads(r.content)
        assert u'&#34;name&#34;: &#34;W2MO\u017d&#34;' in data['content']

    @mock.patch('mkt.reviewers.views.requests.get')
    def test_manifest_json_encoding_empty(self, mock_get):
        m = mock.Mock()
        m.content = ''
        m.headers = CaseInsensitiveDict({})
        mock_get.return_value = m

        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        eq_(json.loads(r.content), {'content': u'', 'headers': {},
                                    'success': True, 'permissions': {}})

    @mock.patch('mkt.reviewers.views.requests.get')
    def test_manifest_json_traceback_in_response(self, mock_get):
        m = mock.Mock()
        m.content = {'name': 'Some name'}
        m.headers = CaseInsensitiveDict({})
        mock_get.side_effect = requests.exceptions.SSLError
        mock_get.return_value = m

        # We should not 500 on a traceback.

        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        data = json.loads(r.content)
        assert data['content'], 'There should be a content with the traceback'
        eq_(data['headers'], {})

    @mock.patch('mkt.reviewers.views.json.dumps')
    def test_manifest_json_packaged(self, mock_):
        # Test that when the app is packaged, _mini_manifest is called.
        mock_.return_value = '{}'

        self.get_app().update(is_packaged=True)
        res = self.client.get(reverse('reviewers.apps.review.manifest',
                                      args=[self.app.app_slug]))
        eq_(res.status_code, 200)
        assert mock_.called

    @mock.patch('mkt.reviewers.views._get_manifest_json')
    def test_manifest_json_perms(self, mock_):
        mock_.return_value = {
            'permissions': {
                "foo": {"description": "foo"},
                "camera": {"description": "<script>"}
            }
        }

        self.get_app().update(is_packaged=True)
        r = self.client.get(reverse('reviewers.apps.review.manifest',
                                    args=[self.app.app_slug]))
        eq_(r.status_code, 200)
        eq_(json.loads(r.content)['permissions'],
            {'foo': {'description': 'foo', 'type': 'web'},
             'camera': {'description': '&lt;script&gt;', 'type': 'priv'}})

    def test_abuse(self):
        AbuseReport.objects.create(addon=self.app, message='!@#$')
        res = self.client.get(self.url)
        doc = pq(res.content)
        dd = doc('.reviewers-desktop #summary dd.abuse-reports')
        eq_(dd.text(), u'1')
        eq_(dd.find('a').attr('href'), reverse('reviewers.apps.review.abuse',
                                               args=[self.app.app_slug]))
        dd = doc('.reviewers-mobile #summary dd.abuse-reports')
        eq_(dd.text(), u'1')
        eq_(dd.find('a').attr('href'), reverse('reviewers.apps.review.abuse',
                                               args=[self.app.app_slug]))

    def _attachment_form_data(self, num=1, action='comment'):
        data = {'action': action,
                'comments': 'mmm, nice app'}
        data.update(self._attachment_management_form(num=num))
        data.update(self._attachments(num))
        return data

    @override_settings(REVIEWER_ATTACHMENTS_PATH=ATTACHMENTS_DIR)
    @mock.patch('mkt.site.storage_utils.LocalFileStorage.save')
    def test_no_attachments(self, save_mock):
        """ Test addition of no attachment """
        data = self._attachment_form_data(num=0, action='public')
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(save_mock.called, False, save_mock.call_args_list)

    def test_idn_app_domain(self):
        response = self.client.get(self.url)
        assert 'IDN domain!' not in response.content

        self.get_app().update(app_domain=u'http://www.allïzom.org')
        response = self.client.get(self.url)
        assert 'IDN domain!' in response.content

    def test_xss_domain(self):
        # It shouldn't be possible to have this in app domain, it will never
        # validate, but better safe than sorry.
        self.get_app().update(app_domain=u'<script>alert(42)</script>')
        response = self.client.get(self.url)
        assert '<script>alert(42)</script>' not in response.content
        assert '&lt;script&gt;alert(42)&lt;/script&gt;' in response.content

    def test_priority_flag_cleared_for_public(self):
        self.get_app().update(priority_review=True)
        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(self.get_app().priority_review, False)

    def test_priority_flag_uncleared_for_reject(self):
        self.get_app().update(priority_review=True)
        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(self.get_app().priority_review, True)

    def test_versions_history_pagination(self):
        self.app.update(is_packaged=True)
        version_factory(addon=self.app, version='2.0')
        version_factory(addon=self.app, version='3.0')

        # Mock paginate to paginate with only 2 versions to limit the
        # number of versions this test has to create.
        with mock.patch('mkt.reviewers.views.paginate',
                        lambda req, objs, limit: paginate(req, objs, 2)):
            content = pq(self.client.get(self.url).content)
        eq_(len(content('#review-files tr.listing-body')), 2)
        eq_(len(content('#review-files-paginate a[rel=next]')), 1)
        eq_(len(content('#review-files-paginate a[rel=prev]')), 0)
        link = content('#review-files-paginate a[rel=next]')[0].attrib['href']
        eq_(link, '%s?page=2#history' % self.url)

        # Look at page 2.
        with mock.patch('mkt.reviewers.views.paginate',
                        lambda req, objs, limit: paginate(req, objs, 2)):
            content = pq(self.client.get(link).content)
        eq_(len(content('#review-files tr.listing-body')), 1)
        eq_(len(content('#review-files-paginate a[rel=next]')), 0)
        eq_(len(content('#review-files-paginate a[rel=prev]')), 1)
        eq_(content('#review-files-paginate a[rel=prev]')[0].attrib['href'],
            '%s?page=1#history' % self.url)


class TestCannedResponses(AppReviewerTest):

    def setUp(self):
        super(TestCannedResponses, self).setUp()
        self.login_as_editor()
        self.app = app_factory(name='XXX', status=mkt.STATUS_PENDING)
        self.cr = CannedResponse.objects.create(
            name=u'app reason', response=u'app reason body',
            sort_group=u'public')
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

    def test_ok(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        form = r.context['form']
        choices = form.fields['canned_response'].choices[1][1]
        # choices is grouped by the sort_group, where choices[0] is the
        # default "Choose a response..." option.
        # Within that, it's paired by [group, [[response, name],...]].
        # So above, choices[1][1] gets the first real group's list of
        # responses.
        eq_(len(choices), 1)
        assert self.cr.response in choices[0]


@mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
@mock.patch('mkt.reviewers.views.messages.success')
@mock.patch('mkt.webapps.tasks.index_webapps')
@mock.patch('mkt.webapps.tasks.update_cached_manifests')
@mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
@mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
class TestApproveHostedApp(AppReviewerTest, TestReviewMixin,
                           AttachmentManagementMixin, TestedonManagementMixin):
    """
    A separate test class for apps going to an approved state. All other state
    transitions are tested above.

    We're doing this to make the mocks easier to handle.

    """
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestApproveHostedApp, self).setUp()
        self.mozilla_contact = 'contact@mozilla.com'
        self.app = self.get_app()
        self.file = self.app.latest_version.files.all()[0]
        self.file.update(status=mkt.STATUS_PENDING)
        self.app.update(status=mkt.STATUS_PENDING,
                        mozilla_contact=self.mozilla_contact,
                        _current_version=None)
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

    def get_app(self):
        return Webapp.objects.get(id=337141)

    def _check_message(self, msg):
        eq_(msg.call_args_list[0][0][1],
            '"Web App Review" successfully processed (+60 points, 60 total).')

    def test_pending_to_public(self, update_name, update_locales,
                               update_cached_manifests,
                               index_webapps, messages, storefront_mock):
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)
        self._check_message(messages)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)

        eq_(update_name.call_count, 0)  # Not a packaged app.
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        # App is not packaged, no need to call update_cached_manifests.
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 1)

    def test_pending_to_hidden(self, update_name, update_locales,
                               update_cached_manifests, index_webapps,
                               messages, storefront_mock):
        self.get_app().update(publish_type=mkt.PUBLISH_HIDDEN)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_UNLISTED)
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)
        self._check_message(messages)

        eq_(update_name.call_count, 0)  # Not a packaged app.
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        # App is not packaged, no need to call update_cached_manifests.
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 1)

    def test_pending_to_approved(self, update_name, update_locales,
                                 update_cached_manifests, index_webapps,
                                 messages, storefront_mock):
        self.get_app().update(publish_type=mkt.PUBLISH_PRIVATE)
        index_webapps.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        # File status is PUBLIC since it is the only version.
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)
        self._check_message(messages)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)

        # The app is not private but can still be installed by team members,
        # so we should call those:
        eq_(update_name.call_count, 0)  # Not a packaged app.
        eq_(update_locales.call_count, 1)
        # App is not packaged, no need to call update_cached_manifests.
        eq_(update_cached_manifests.delay.call_count, 0)
        # App is private so we don't send this yet.
        eq_(storefront_mock.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)

    def test_pending_to_reject(self, update_name, update_locales,
                               update_cached_manifests, index_webapps,
                               messages, storefront_mock):
        index_webapps.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)

        data = {'action': 'reject', 'comments': 'suxor'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        eq_(index_webapps.delay.call_count, 1)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_REJECTED)
        eq_(self.file.reload().status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.REJECT_VERSION)
        self._check_message(messages)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_HOSTED)

        eq_(update_name.call_count, 0)  # Not a packaged app.
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)


@mock.patch('lib.crypto.packaged.sign')
@mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
@mock.patch('mkt.reviewers.views.messages.success')
@mock.patch('mkt.webapps.tasks.index_webapps')
@mock.patch('mkt.webapps.tasks.update_cached_manifests')
@mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
@mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
class TestApprovePackagedApp(AppReviewerTest, TestReviewMixin,
                             AttachmentManagementMixin,
                             TestedonManagementMixin):
    """
    A separate test class for packaged apps going to an approved state.

    We're doing this to make the mocks easier to handle.

    """
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestApprovePackagedApp, self).setUp()
        self.mozilla_contact = 'contact@mozilla.com'
        self.app = self.get_app()
        self.file = self.app.latest_version.files.all()[0]
        self.file.update(status=mkt.STATUS_PENDING)
        self.app.update(status=mkt.STATUS_PENDING,
                        mozilla_contact=self.mozilla_contact,
                        _current_version=None, is_packaged=True)
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

    def get_app(self):
        return Webapp.objects.get(id=337141)

    def _check_message(self, msg):
        eq_(msg.call_args_list[0][0][1],
            '"Packaged App Review" successfully processed '
            '(+60 points, 60 total).')

    def test_pending_to_public(self, update_name, update_locales,
                               update_cached_manifests, index_webapps,
                               messages, storefront_mock, sign_mock):
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_PACKAGED)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 1)
        eq_(sign_mock.call_args[0][0], self.get_app().current_version.pk)

    def test_pending_to_hidden(self, update_name, update_locales,
                               update_cached_manifests, index_webapps,
                               messages, storefront_mock, sign_mock):
        self.get_app().update(publish_type=mkt.PUBLISH_HIDDEN)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_UNLISTED)
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_PACKAGED)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 1)
        eq_(sign_mock.call_args[0][0], self.get_app().current_version.pk)

    def test_pending_to_approved(self, update_name, update_locales,
                                 update_cached_manifests, index_webapps,
                                 messages, storefront_mock, sign_mock):
        self.get_app().update(publish_type=mkt.PUBLISH_PRIVATE)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        eq_(self.file.reload().status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_PACKAGED)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_args[0][0], self.get_app().current_version.pk)

    def test_pending_to_rejected(self, update_name, update_locales,
                                 update_cached_manifests, index_webapps,
                                 messages, storefront_mock, sign_mock):
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_REJECTED)
        eq_(self.file.reload().status, mkt.STATUS_DISABLED)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_PACKAGED)
        self._check_message(messages)

        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_count, 0)

    def test_pending_to_approved_app_private_prior_version_rejected(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        """
        Test that everything works out ok when v1.0 was rejected and developer
        submitted v1.1 that is then approved. This should still be considered a
        packaged review (not an update) and set the approved version to PUBLIC
        since the proir verison is DISABLED. See bug 1075042.
        """
        self.app.update(status=mkt.STATUS_REJECTED,
                        publish_type=mkt.PUBLISH_PRIVATE)
        self.file.update(status=mkt.STATUS_DISABLED)
        self.new_version = version_factory(
            addon=self.app, version='1.1',
            file_kw={'status': mkt.STATUS_PENDING})

        index_webapps.delay.reset_mock()
        update_cached_manifests.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        eq_(self.app.current_version, None)
        eq_(self.app.latest_version, self.new_version)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        eq_(app.latest_version, self.new_version)
        eq_(app.current_version, self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_PACKAGED)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_args[0][0], self.new_version.pk)


@mock.patch('lib.crypto.packaged.sign')
@mock.patch('mkt.webapps.models.Webapp.set_iarc_storefront_data')
@mock.patch('mkt.reviewers.views.messages.success')
@mock.patch('mkt.webapps.tasks.index_webapps')
@mock.patch('mkt.webapps.tasks.update_cached_manifests')
@mock.patch('mkt.webapps.models.Webapp.update_supported_locales')
@mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
class TestApprovePackagedVersions(AppReviewerTest, TestReviewMixin,
                                  AttachmentManagementMixin,
                                  TestedonManagementMixin):
    """
    A separate test class for packaged apps with a 2nd version going to an
    approved state.

    We're doing this to make the mocks easier to handle.

    """
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestApprovePackagedVersions, self).setUp()
        self.mozilla_contact = 'contact@mozilla.com'
        self.app = self.get_app()
        self.file = self.app.latest_version.files.all()[0]
        self.app.update(status=mkt.STATUS_PUBLIC,
                        mozilla_contact=self.mozilla_contact,
                        is_packaged=True)
        self.new_version = version_factory(
            addon=self.app, version='2.0',
            file_kw={'status': mkt.STATUS_PENDING})
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

    def get_app(self):
        return Webapp.objects.get(id=337141)

    def _check_message(self, msg):
        eq_(msg.call_args_list[0][0][1],
            '"Updated Packaged App Review" successfully processed '
            '(+40 points, 40 total).')

    def test_version_pending_to_public(self, update_name, update_locales,
                                       update_cached_manifests, index_webapps,
                                       messages, storefront_mock, sign_mock):
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        eq_(app.current_version, self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 1)
        eq_(sign_mock.call_args[0][0], app.current_version.pk)

    def test_version_pending_to_approved(self, update_name, update_locales,
                                         update_cached_manifests,
                                         index_webapps, messages,
                                         storefront_mock, sign_mock):
        self.app.update(publish_type=mkt.PUBLISH_PRIVATE)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_APPROVED)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_args[0][0], self.new_version.pk)

    def test_version_pending_to_public_app_unlisted(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_UNLISTED)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_UNLISTED)
        eq_(app.current_version, self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 1)
        eq_(sign_mock.call_args[0][0], app.current_version.pk)

    def test_version_pending_to_approved_app_unlisted(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_UNLISTED,
                        publish_type=mkt.PUBLISH_PRIVATE)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_UNLISTED)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_APPROVED)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_args[0][0], self.new_version.pk)

    def test_version_pending_to_public_app_private(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_APPROVED)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        eq_(app.current_version, self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        self._check_log(mkt.LOG.APPROVE_VERSION)

        self._check_email_dev_and_contact('Approved')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 1)
        eq_(sign_mock.call_args[0][0], app.current_version.pk)

    def test_version_pending_to_approved_app_private(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_APPROVED,
                        publish_type=mkt.PUBLISH_PRIVATE)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'public', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_APPROVED)
        self._check_log(mkt.LOG.APPROVE_VERSION_PRIVATE)

        self._check_email_dev_and_contact('Approved but private')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 1)
        eq_(update_locales.call_count, 1)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 1)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_args[0][0], self.new_version.pk)

    def test_version_pending_to_rejected_app_public(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_PUBLIC)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_PUBLIC)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.REJECT_VERSION)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_count, 0)

    def test_version_pending_to_rejected_app_unlisted(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_UNLISTED)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_UNLISTED)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.REJECT_VERSION)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_count, 0)

    def test_version_pending_to_rejected_app_private(
            self, update_name, update_locales, update_cached_manifests,
            index_webapps, messages, storefront_mock, sign_mock):
        self.app.update(status=mkt.STATUS_APPROVED)
        index_webapps.delay.reset_mock()
        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)

        data = {'action': 'reject', 'comments': 'something'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self.post(data)
        app = self.get_app()
        eq_(app.status, mkt.STATUS_APPROVED)
        ok_(app.current_version != self.new_version)
        eq_(app.current_version.all_files[0].status, mkt.STATUS_PUBLIC)
        eq_(self.new_version.all_files[0].status, mkt.STATUS_DISABLED)
        self._check_log(mkt.LOG.REJECT_VERSION)

        self._check_email_dev_and_contact('Rejected')
        self._check_email_body()
        self._check_score(mkt.REVIEWED_WEBAPP_UPDATE)
        self._check_message(messages)

        eq_(update_name.call_count, 0)
        eq_(update_locales.call_count, 0)
        eq_(index_webapps.delay.call_count, 1)
        eq_(update_cached_manifests.delay.call_count, 0)
        eq_(storefront_mock.call_count, 0)
        eq_(sign_mock.call_count, 0)


class TestReviewLog(AppReviewerTest, AccessMixin):

    def setUp(self):
        super(TestReviewLog, self).setUp()
        # Note: if `created` is not specified, `app_factory` uses a randomly
        # generated timestamp.
        self.apps = [app_factory(name='XXX', created=days_ago(3),
                                 status=mkt.STATUS_PENDING),
                     app_factory(name='YYY', created=days_ago(2),
                                 status=mkt.STATUS_PENDING)]
        self.url = reverse('reviewers.apps.logs')

        patcher = mock.patch.object(settings, 'TASK_USER_ID',
                                    self.admin_user.id)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_user(self):
        return self.reviewer_user

    def make_approvals(self):
        d = 1
        for app in self.apps:
            days_ago = self.days_ago(d)
            mkt.log(mkt.LOG.REJECT_VERSION, app, app.latest_version,
                    user=self.get_user(), details={'comments': 'youwin'},
                    created=days_ago)
            # Throw in a few tasks logs that shouldn't get queried.
            mkt.log(mkt.LOG.REREVIEW_MANIFEST_CHANGE, app, app.latest_version,
                    user=self.admin_user, details={'comments': 'foo'},
                    created=days_ago)
            d += 1

    def make_an_approval(self, action, comment='youwin', user=None, app=None):
        if not user:
            user = self.get_user()
        if not app:
            app = self.apps[0]
        mkt.log(action, app, app.latest_version, user=user,
                details={'comments': comment})

    def test_basic(self):
        self.make_approvals()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        assert doc('#log-filter button'), 'No filters.'

        # Should have 2 showing.
        rows = doc('tbody tr')
        logs = rows.filter(':not(.hide)')
        eq_(logs.length, 2)

        # Ensure that the app links are valid.
        eq_(logs.find('.name .app-link').eq(0).attr('href'),
            self.apps[0].get_url_path())
        eq_(logs.find('.name .app-link').eq(1).attr('href'),
            self.apps[1].get_url_path())

        eq_(rows.filter('.hide').eq(0).text(), 'youwin')

    def test_search_app_soft_deleted(self):
        self.make_approvals()
        self.apps[0].update(status=mkt.STATUS_DELETED)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        all_reviews = [d.attrib.get('data-addonid')
                       for d in doc('#log-listing tbody tr')]
        assert str(self.apps[0].pk) in all_reviews, (
            'Soft deleted review did not show up in listing')

    def test_xss(self):
        a = self.apps[0]
        a.name = '<script>alert("xss")</script>'
        a.save()
        mkt.log(mkt.LOG.REJECT_VERSION, a, a.latest_version,
                user=self.get_user(), details={'comments': 'xss!'})

        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        inner_html = pq(r.content)('#log-listing tbody td').eq(1).html()

        assert '&lt;script&gt;' in inner_html
        assert '<script>' not in inner_html

    def test_end_filter(self):
        """
        Let's use today as an end-day filter and make sure we see stuff if we
        filter.
        """
        self.make_approvals()
        # Make sure we show the stuff we just made.
        date = time.strftime('%Y-%m-%d')
        r = self.client.get(self.url, dict(end=date))
        eq_(r.status_code, 200)
        doc = pq(r.content)('#log-listing tbody')
        eq_(doc('tr:not(.hide)').length, 2)
        eq_(doc('tr.hide').eq(0).text(), 'youwin')

    def test_end_filter_wrong(self):
        """
        Let's use today as an end-day filter and make sure we see stuff if we
        filter.
        """
        self.make_approvals()
        r = self.client.get(self.url, dict(end='wrong!'))
        # If this is broken, we'll get a traceback.
        eq_(r.status_code, 200)
        eq_(pq(r.content)('#log-listing tr:not(.hide)').length, 3)

    def test_search_comment_exists(self):
        """Search by comment."""
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL, comment='hello')
        r = self.client.get(self.url, dict(search='hello'))
        eq_(r.status_code, 200)
        eq_(pq(r.content)('#log-listing tbody tr.hide').eq(0).text(), 'hello')

    def test_search_comment_doesnt_exist(self):
        """Search by comment, with no results."""
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL, comment='hello')
        r = self.client.get(self.url, dict(search='bye'))
        eq_(r.status_code, 200)
        eq_(pq(r.content)('.no-results').length, 1)

    def test_search_author_exists(self):
        """Search by author."""
        self.make_approvals()
        user = UserProfile.objects.get(email='regular@mozilla.com')
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL, user=user, comment='hi')

        r = self.client.get(self.url, dict(search='regular'))
        eq_(r.status_code, 200)
        rows = pq(r.content)('#log-listing tbody tr')

        eq_(rows.filter(':not(.hide)').length, 1)
        eq_(rows.filter('.hide').eq(0).text(), 'hi')

    def test_search_author_doesnt_exist(self):
        """Search by author, with no results."""
        self.make_approvals()
        user = UserProfile.objects.get(email='editor@mozilla.com')
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL, user=user)

        r = self.client.get(self.url, dict(search='wrong'))
        eq_(r.status_code, 200)
        eq_(pq(r.content)('.no-results').length, 1)

    def test_search_addon_exists(self):
        """Search by add-on name."""
        self.make_approvals()
        app = self.apps[0]
        r = self.client.get(self.url, dict(search=app.name))
        eq_(r.status_code, 200)
        tr = pq(r.content)('#log-listing tr[data-addonid="%s"]' % app.id)
        eq_(tr.length, 1)
        eq_(tr.siblings('.comments').text(), 'youwin')

    def test_search_addon_by_slug_exists(self):
        """Search by app slug."""
        app = self.apps[0]
        app.app_slug = 'a-fox-was-sly'
        app.save()
        self.make_approvals()
        r = self.client.get(self.url, dict(search='fox'))
        eq_(r.status_code, 200)
        tr = pq(r.content)('#log-listing tr[data-addonid="%s"]' % app.id)
        eq_(tr.length, 1)
        eq_(tr.siblings('.comments').text(), 'youwin')

    def test_search_addon_doesnt_exist(self):
        """Search by add-on name, with no results."""
        self.make_approvals()
        r = self.client.get(self.url, dict(search='zzz'))
        eq_(r.status_code, 200)
        eq_(pq(r.content)('.no-results').length, 1)

    @mock.patch('mkt.developers.models.ActivityLog.arguments', new=mock.Mock)
    def test_addon_missing(self):
        self.make_approvals()
        r = self.client.get(self.url)
        eq_(pq(r.content)('#log-listing tr td').eq(1).text(),
            'App has been deleted.')

    def test_request_info_logs(self):
        self.make_an_approval(mkt.LOG.REQUEST_INFORMATION)
        r = self.client.get(self.url)
        eq_(pq(r.content)('#log-listing tr td a').eq(1).text(),
            'More information requested')

    def test_escalate_logs(self):
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL)
        r = self.client.get(self.url)
        eq_(pq(r.content)('#log-listing tr td a').eq(1).text(),
            'Reviewer escalation')

    def test_no_double_encode(self):
        version = self.apps[0].latest_version
        version.update(version='<foo>')
        self.make_an_approval(mkt.LOG.ESCALATE_MANUAL)
        r = self.client.get(self.url)
        assert '<foo>' in pq(r.content)('#log-listing tr td').eq(1).text(), (
            'Double-encoded string was found in reviewer log.')


class TestMotd(AppReviewerTest, AccessMixin):

    def setUp(self):
        super(TestMotd, self).setUp()
        self.url = reverse('reviewers.apps.motd')
        self.key = u'mkt_reviewers_motd'
        set_config(self.key, u'original value')

    def test_perms_not_editor(self):
        self.client.logout()
        req = self.client.get(self.url, follow=True)
        self.assert3xx(req, '%s?to=%s' % (reverse('users.login'), self.url))
        self.client.login('regular@mozilla.com')
        eq_(self.client.get(self.url).status_code, 403)

    def test_perms_not_motd(self):
        # Any type of reviewer can see the MOTD.
        self.login_as_editor()
        req = self.client.get(self.url)
        eq_(req.status_code, 200)
        eq_(req.context['form'], None)
        # No redirect means it didn't save.
        eq_(self.client.post(self.url, dict(motd='motd')).status_code, 200)
        eq_(get_config(self.key), u'original value')

    def test_motd_change(self):
        # Only users in the MOTD group can POST.
        user = self.reviewer_user
        self.grant_permission(user, 'AppReviewerMOTD:Edit')
        self.login_as_editor()

        # Get is a 200 with a form.
        req = self.client.get(self.url)
        eq_(req.status_code, 200)
        eq_(req.context['form'].initial['motd'], u'original value')
        # Empty post throws an error.
        req = self.client.post(self.url, dict(motd=''))
        eq_(req.status_code, 200)  # Didn't redirect after save.
        eq_(pq(req.content)('#editor-motd .errorlist').text(),
            'This field is required.')
        # A real post now.
        req = self.client.post(self.url, dict(motd='new motd'))
        self.assert3xx(req, self.url)
        eq_(get_config(self.key), u'new motd')


class TestReviewAppComm(AppReviewerTest, AttachmentManagementMixin,
                        TestReviewMixin, TestedonManagementMixin):
    """
    Integration test that notes are created and that emails are
    sent to the right groups of people.
    """

    def setUp(self):
        super(TestReviewAppComm, self).setUp()
        self.app = app_factory(rated=True, status=mkt.STATUS_PENDING,
                               mozilla_contact='contact@mozilla.com')
        self.app.addonuser_set.create(user=user_factory(email='steamcube'))
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

        self.mozilla_contact = 'contact@mozilla.com'

    def _post(self, data, queue='pending'):
        res = self.client.post(self.url, data)
        self.assert3xx(res, reverse('reviewers.apps.queue_%s' % queue))

    def _get_note(self):
        eq_(self.app.threads.count(), 1)
        thread = self.app.threads.all()[0]
        eq_(thread.notes.count(), 1)
        return thread.notes.all()[0]

    def test_email_cc(self):
        """
        Emailed cc'ed people (those who have posted on the thread).
        """
        poster = user_factory()
        thread, note = create_comm_note(
            self.app, self.app.latest_version, poster, 'lgtm')

        data = {'action': 'public', 'comments': 'gud jerb'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test emails.
        self._check_email_dev_and_contact(None, outbox_len=5)

        # Some person who joined the thread.
        self._check_email(
            self._get_mail(poster.email), 'Approved', to=[poster.email])

    def test_approve(self):
        """
        On approval, send an email to [developer, mozilla contact].
        """
        data = {'action': 'public', 'comments': 'gud jerb'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.APPROVAL)
        eq_(note.body, 'gud jerb')

        # Test emails.
        self._check_email_dev_and_contact(None)

    def test_reject(self):
        """
        On rejection, send an email to [developer, mozilla contact].
        """
        data = {'action': 'reject', 'comments': 'rubesh'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.REJECTION)
        eq_(note.body, 'rubesh')

        # Test emails.
        self._check_email_dev_and_contact(None)

    def test_info(self):
        """
        On info request, send an email to [developer, mozilla contact].
        """
        data = {'action': 'info', 'comments': 'huh'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.MORE_INFO_REQUIRED)
        eq_(note.body, 'huh')

        # Test emails.
        self._check_email_dev_and_contact(None)

    def test_escalate(self):
        """
        On escalation, send an email to senior reviewers and developer.
        """
        data = {'action': 'escalate', 'comments': 'soup her man'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.ESCALATION)
        eq_(note.body, 'soup her man')

        # Test emails.
        eq_(len(mail.outbox), 2)
        self._check_email(  # Senior reviewer.
            self._get_mail(self.snr_reviewer_user.email), 'Escalated',
            to=[self.snr_reviewer_user.email])
        self._check_email(self._get_mail('steamcube'), 'Escalated')

    def test_comment(self):
        """
        On reviewer comment, send an email to those but developers.
        """
        data = {'action': 'comment', 'comments': 'huh'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.REVIEWER_COMMENT)
        eq_(note.body, 'huh')

        # Test emails.
        eq_(len(mail.outbox), 1)

        self._check_email(mail.outbox[0], 'Private reviewer comment',
                          to=[self.mozilla_contact])

    def test_disable(self):
        """
        On banning, send an email to [developer, mozilla contact].
        """
        self.login_as_admin()
        data = {'action': 'disable', 'comments': 'u dun it'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.DISABLED)
        eq_(note.body, 'u dun it')

        # Test emails.
        self._check_email_dev_and_contact(None)

    def test_attachments(self):
        data = {'action': 'comment', 'comments': 'huh'}
        data.update(self._attachment_management_form(num=2))
        data.update(self._attachments(num=2))
        data.update(self._testedon_management_form())
        self._post(data)

        # Test attachments.
        note = self._get_note()
        eq_(note.attachments.count(), 2)

    def test_tested_on_one(self):
        """Tested 'Tested on' message appended to note body."""
        data = {'action': 'reject', 'comments': 'rubesh'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form(num=1))
        data.update(self._platforms(1))
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.REJECTION)
        eq_(note.body, u'rubesh\n\n'
            u'Tested on \xd0esktop platform on PC with version 34')

    def test_tested_on_two(self):
        """Tested two 'Tested on' messages appended to note body."""
        data = {'action': 'reject', 'comments': 'rubesh'}
        data.update(self._attachment_management_form(num=0))
        data.update(self._testedon_management_form(num=2))
        data.update(self._platforms(2))
        self._post(data)

        # Test notes.
        note = self._get_note()
        eq_(note.note_type, comm.REJECTION)
        eq_(note.body, u'rubesh\n\n'
            u'Tested on \xd0esktop platform on PC with version 34; '
            u'FirefoxOS platform on ZT\xc8 Open with version 1.3<')


class TestModeratedQueue(mkt.site.tests.TestCase, AccessMixin):

    def setUp(self):
        super(TestModeratedQueue, self).setUp()

        self.app = app_factory()

        self.moderator_user = user_factory(email='moderator')
        self.grant_permission(self.moderator_user, 'Apps:ModerateReview')
        user_factory(email='regular')

        user1 = user_factory()
        user2 = user_factory()

        self.url = reverse('reviewers.apps.queue_moderated')

        self.review1 = Review.objects.create(addon=self.app, body='body',
                                             user=user1, rating=3,
                                             editorreview=True)
        ReviewFlag.objects.create(review=self.review1, flag=ReviewFlag.SPAM,
                                  user=user1)
        self.review2 = Review.objects.create(addon=self.app, body='body',
                                             user=user2, rating=4,
                                             editorreview=True)
        ReviewFlag.objects.create(review=self.review2, flag=ReviewFlag.SUPPORT,
                                  user=user2)
        self.login(self.moderator_user)

    def _post(self, action):
        ctx = self.client.get(self.url).context
        data_formset = formset(initial(ctx['reviews_formset'].forms[0]))
        data_formset['form-0-action'] = action

        res = self.client.post(self.url, data_formset)
        self.assert3xx(res, self.url)

    def _get_logs(self, action):
        return ActivityLog.objects.filter(action=action.id)

    def test_anonymous_flagger(self):
        ReviewFlag.objects.all()[0].update(user=None)
        ReviewFlag.objects.all()[1].delete()
        res = self.client.get(self.url)
        txt = pq(res.content)('.reviews-flagged-reasons li div span').text()
        teststring = u'Flagged by an anonymous user on'
        ok_(txt.startswith(teststring),
            '"%s" doesn\'t start with "%s"' % (txt, teststring))

    def test_setup(self):
        eq_(Review.objects.filter(editorreview=True).count(), 2)
        eq_(ReviewFlag.objects.filter(flag=ReviewFlag.SPAM).count(), 1)

        res = self.client.get(self.url)
        doc = pq(res.content)('#reviews-flagged')

        # Test the default action is "skip".
        eq_(doc('.reviewers-desktop #id_form-0-action_1:checked').length, 1)

    def test_skip(self):
        # Skip the first review, which still leaves two.
        self._post(mkt.ratings.REVIEW_MODERATE_SKIP)
        res = self.client.get(self.url)
        eq_(len(res.context['page'].object_list), 2)

    def test_delete(self):
        # Delete the first review, which leaves one.
        self._post(mkt.ratings.REVIEW_MODERATE_DELETE)
        res = self.client.get(self.url)
        eq_(len(res.context['page'].object_list), 1)
        eq_(self._get_logs(mkt.LOG.DELETE_REVIEW).count(), 1)

    def test_keep(self):
        # Keep the first review, which leaves one.
        self._post(mkt.ratings.REVIEW_MODERATE_KEEP)
        res = self.client.get(self.url)
        eq_(len(res.context['page'].object_list), 1)
        eq_(self._get_logs(mkt.LOG.APPROVE_REVIEW).count(), 1)

    def test_no_reviews(self):
        Review.objects.all().delete()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(pq(res.content)('#reviews-flagged .no-results').length, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('.tabnav li a')[0].text, u'Moderated Reviews (2)')

    def test_queue_count_reviewer_and_moderator(self):
        self.grant_permission(self.moderator_user, 'Apps:Review')
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Reviewing (0)')
        eq_(links[4].text, u'Moderated Reviews (2)')

    def test_deleted_app(self):
        "Test that a deleted app doesn't break the queue."
        self.app.delete()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_queue_count_deleted_app(self):
        self.app.delete()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('.tabnav li a')[0].text, u'Moderated Reviews (0)')


class AbuseQueueMixin(object):

    def _setUp(self):
        self.abuseviewer_user = user_factory(email='abuser')
        self.grant_permission(self.abuseviewer_user, self.perm)
        self.login(self.abuseviewer_user)
        user_factory(email='regular')

        self.url = reverse(self.view_name)

    def _post(self, action, form_index=0):
        ctx = self.client.get(self.url).context
        data_formset = formset(initial(ctx['abuse_formset'].forms[0]))
        data_formset['form-%s-action' % (form_index)] = action

        res = self.client.post(self.url, data_formset)
        self.assert3xx(res, self.url)

    def _get_logs(self, action):
        return ActivityLog.objects.filter(action=action.id)

    def test_anonymous_flagger(self):
        AbuseReport.objects.all()[0].update(reporter=None)
        res = self.client.get(self.url)
        txt = pq(res.content)('.abuse-reports-reports li div span').text()
        teststring = u'Submitted by an anonymous user on'
        ok_(txt.startswith(teststring),
            '"%s" doesn\'t start with "%s"' % (txt, teststring))

    def test_no_reviews(self):
        AbuseReport.objects.all().delete()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(pq(res.content)('#abuse-reports .no-results').length, 1)

    def test_queue_count(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        txt = pq(r.content)('.tabnav li a')[0].text
        teststring = u'Abuse Reports (2)'
        ok_(txt.endswith(teststring),
            '"%s" doesn\'t start with "%s"' % (txt, teststring))

    def test_skip(self):
        # Skip the first xxx's reports, which still leaves 2 apps/sites.
        self._post(mkt.abuse.forms.ABUSE_REPORT_SKIP)
        res = self.client.get(self.url)
        eq_(len(res.context['page'].object_list), 2)

    def test_first_read(self):
        # Mark read the first xxx's reports, which leaves one.
        self._post(mkt.abuse.forms.ABUSE_REPORT_READ)
        res = self.client.get(self.url)
        eq_(len(res.context['page'].object_list), 1)
        # There are two abuse reports for app1/website1, so two log entries.
        eq_(self._get_logs(self.log_const).count(), 2)
        # Check the remaining abuse report remains unread.
        eq_(AbuseReport.objects.filter(read=False).count(), 1)

    def test_first_flag(self):
        # Flag the first xxx's reports.
        self._post(mkt.abuse.forms.ABUSE_REPORT_FLAG)
        res = self.client.get(self.url)
        # Check one is left.
        eq_(len(res.context['page'].object_list), 1)
        # Check the object is flagged.
        eq_(RereviewQueue.objects.count(), 1)
        # As flagging marks read too, there should be 2 log entries.
        eq_(self._get_logs(self.log_const).count(), 2)
        # Check the remaining abuse report remains unread.
        eq_(AbuseReport.objects.filter(read=False).count(), 1)

    def test_xss(self):
        xss = '<script>alert("xss")</script>'
        AbuseReport.objects.all()[0].update(message=xss)
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        tbody = pq(res.content)(
            '#abuse-reports .abuse-reports-reports').html()
        assert '&lt;script&gt;' in tbody
        assert '<script>' not in tbody

    def test_deleted_website(self):
        "Test that a deleted app/website doesn't break the queue."
        AbuseReport.objects.all()[0].object.delete()
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        txt = pq(r.content)('.tabnav li a')[0].text
        teststring = u'Abuse Reports (1)'
        ok_(txt.endswith(teststring),
            '"%s" doesn\'t start with "%s"' % (txt, teststring))


class TestAppAbuseQueue(mkt.site.tests.TestCase, AccessMixin,
                        AbuseQueueMixin):
    perm = 'Apps:ReadAbuse'
    view_name = 'reviewers.apps.queue_abuse'
    log_const = mkt.LOG.APP_ABUSE_MARKREAD

    def setUp(self):
        super(TestAppAbuseQueue, self).setUp()
        self._setUp()

    @classmethod
    def setUpTestData(cls):
        app1 = app_factory()
        app2 = app_factory()
        # Add some extra apps, which shouldn't show up.
        app_factory()
        app_factory()

        user1 = user_factory()
        user2 = user_factory()

        AbuseReport.objects.create(reporter=user1, ip_address='123.45.67.89',
                                   addon=app1, message='bad')
        AbuseReport.objects.create(reporter=user2, ip_address='123.01.67.89',
                                   addon=app1, message='terrible')
        AbuseReport.objects.create(reporter=user1, ip_address='123.01.02.89',
                                   addon=app2, message='the worst')

    def test_setup(self):
        eq_(AbuseReport.objects.filter(read=False).count(), 3)
        eq_(AbuseReport.objects.filter(addon=Webapp.objects.all()[0]).count(),
            2)

        res = self.client.get(self.url)

        # Check there are 2 apps listed.
        eq_(len(res.context['page'].object_list), 2)

    def test_queue_count_reviewer_and_moderator(self):
        self.grant_permission(self.abuseviewer_user, 'Apps:Review')
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        links = doc('.tabnav li a')
        eq_(links[0].text, u'Apps (0)')
        eq_(links[1].text, u'Re-reviews (0)')
        eq_(links[2].text, u'Updates (0)')
        eq_(links[3].text, u'Reviewing (0)')
        eq_(links[4].text, u'Abuse Reports (2)')


class TestWebsiteAbuseQueue(mkt.site.tests.TestCase, AccessMixin,
                            AbuseQueueMixin):
    perm = 'Websites:ReadAbuse'
    view_name = 'reviewers.websites.queue_abuse'
    log_const = mkt.LOG.WEBSITE_ABUSE_MARKREAD

    def setUp(self):
        super(TestWebsiteAbuseQueue, self).setUp()
        self._setUp()

    @classmethod
    def setUpTestData(cls):
        website1 = website_factory()
        website2 = website_factory()
        # Add some extra sites, which shouldn't show up.
        website_factory()
        website_factory()

        user1 = user_factory()
        user2 = user_factory()

        AbuseReport.objects.create(reporter=user1, ip_address='123.45.67.89',
                                   website=website1, message='bad')
        AbuseReport.objects.create(reporter=user2, ip_address='123.01.67.89',
                                   website=website1, message='terrible')
        AbuseReport.objects.create(reporter=user1, ip_address='123.01.02.89',
                                   website=website2, message='the worst')
        cls.website1 = website1

    def test_setup(self):
        eq_(AbuseReport.objects.filter(read=False).count(), 3)
        eq_(AbuseReport.objects.filter(website=self.website1).count(), 2)

        res = self.client.get(self.url)

        # Check there are 2 websites listed.
        eq_(len(res.context['page'].object_list), 2)

    def test_first_flag(self):
        # No re-review flagging for Websites yet - no re-review queue!
        raise SkipTest()


class TestGetSigned(BasePackagedAppTest, mkt.site.tests.TestCase):

    def setUp(self):
        super(TestGetSigned, self).setUp()
        self.url = reverse('reviewers.signed', args=[self.app.app_slug,
                                                     self.version.pk])
        self.grant_permission(user_factory(email='editor'), 'Apps:Review')
        self.login('editor@mozilla.com')

    def test_not_logged_in(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_not_reviewer(self):
        self.client.logout()
        self.login(user_factory())
        eq_(self.client.get(self.url).status_code, 403)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.LocalFileStorage')
    @mock.patch('lib.crypto.packaged.sign')
    def test_reviewer_sign_arguments_local(self, sign_mock):
        sign_mock.side_effect = mock_sign
        self.setup_files()
        res = self.client.get(self.url)
        sign_mock.assert_called_with(self.version.pk, reviewer=True)
        eq_(res.status_code, 200)

    @override_settings(
        DEFAULT_FILE_STORAGE='mkt.site.storage_utils.S3BotoPrivateStorage')
    @mock.patch('lib.crypto.packaged.sign')
    def test_reviewer_sign_arguments_storage(self, sign_mock):
        sign_mock.side_effect = mock_sign
        self.setup_files()
        res = self.client.get(self.url)
        sign_mock.assert_called_with(self.version.pk, reviewer=True)
        self.assert3xx(res, private_storage.url(
            self.file.signed_reviewer_file_path))

    @mock.patch.object(packaged, 'sign', mock_sign)
    def test_reviewer(self):
        if not settings.XSENDFILE:
            raise SkipTest()

        self.setup_files()
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        file_ = self.app.current_version.all_files[0]
        eq_(res['x-sendfile'], file_.signed_reviewer_file_path)
        eq_(res['etag'], '"%s"' % file_.hash.split(':')[-1])

    def test_not_packaged(self):
        self.app.update(is_packaged=False)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_wrong_version(self):
        self.url = reverse('reviewers.signed', args=[self.app.app_slug, 0])
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_token_good(self):
        if not settings.XSENDFILE:
            raise SkipTest()

        token = Token(data={'app_id': self.app.id})
        token.save()
        self.setup_files()
        self.client.logout()

        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 200)
        file_ = self.app.current_version.all_files[0]
        eq_(res['x-sendfile'], file_.signed_reviewer_file_path)
        eq_(res['etag'], '"%s"' % file_.hash.split(':')[-1])

        # Test token doesn't work the 2nd time.
        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 403)

    def test_token_bad(self):
        token = Token(data={'app_id': 'abcdef'})
        token.save()
        self.setup_files()
        self.client.logout()

        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 403)


class TestMiniManifestView(BasePackagedAppTest):

    def setUp(self):
        super(TestMiniManifestView, self).setUp()
        self.app = Webapp.objects.get(pk=337141)
        self.app.update(is_packaged=True)
        self.version = self.app.versions.latest()
        self.file = self.version.all_files[0]
        self.file.update(filename='mozball.zip')
        self.url = reverse('reviewers.mini_manifest', args=[self.app.app_slug,
                                                            self.version.pk])
        self.grant_permission(user_factory(email='editor'), 'Apps:Review')
        self.login('editor@mozilla.com')

    def test_not_logged_in(self):
        self.client.logout()
        self.assertLoginRequired(self.client.get(self.url))

    def test_not_reviewer(self):
        self.client.logout()
        self.login(user_factory())
        eq_(self.client.get(self.url).status_code, 403)

    def test_not_packaged(self):
        self.app.update(is_packaged=False)
        res = self.client.get(self.url)
        eq_(res.status_code, 404)

    def test_wrong_version(self):
        url = reverse('reviewers.mini_manifest', args=[self.app.app_slug, 0])
        res = self.client.get(url)
        eq_(res.status_code, 404)

    def test_reviewer(self):
        self.setup_files()
        manifest = self.app.get_manifest_json(self.file)

        res = self.client.get(self.url)
        eq_(res['Content-type'], MANIFEST_CONTENT_TYPE)
        data = json.loads(res.content)
        eq_(data['name'], manifest['name'])
        eq_(data['developer']['name'], 'Mozilla Marketplace')
        eq_(data['package_path'],
            absolutify(reverse('reviewers.signed',
                               args=[self.app.app_slug, self.version.id])))

    def test_rejected(self):
        # Rejected sets file.status to DISABLED and moves to a guarded path.
        self.setup_files()
        self.app.update(status=mkt.STATUS_REJECTED)
        self.file.update(status=mkt.STATUS_DISABLED)
        manifest = self.app.get_manifest_json(self.file)

        res = self.client.get(self.url)
        eq_(res['Content-type'], MANIFEST_CONTENT_TYPE)
        data = json.loads(res.content)
        eq_(data['name'], manifest['name'])
        eq_(data['developer']['name'], 'Mozilla Marketplace')
        eq_(data['package_path'],
            absolutify(reverse('reviewers.signed',
                               args=[self.app.app_slug,
                                     self.version.id])))

    def test_minifest_name_matches_manifest_name(self):
        self.setup_files()
        self.app.name = 'XXX'
        self.app.save()
        manifest = self.app.get_manifest_json(self.file)

        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['name'], manifest['name'])

    def test_token_good(self):
        token = Token(data={'app_id': self.app.id})
        token.save()
        self.setup_files()
        self.client.logout()

        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 200)
        eq_(res['Content-type'], MANIFEST_CONTENT_TYPE)
        data = json.loads(res.content)
        ok_('token=' in data['package_path'])

        # Test token doesn't work the 2nd time.
        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 403)

    def test_token_bad(self):
        token = Token(data={'app_id': 'abcdef'})
        token.save()
        self.setup_files()
        self.client.logout()

        res = self.client.get(urlparams(self.url, token=token.token))
        eq_(res.status_code, 403)


class TestReviewersScores(AppReviewerTest, AccessMixin):

    def setUp(self):
        super(TestReviewersScores, self).setUp()
        self.user = self.reviewer_user
        self.url = reverse('reviewers.performance', args=[self.user.email])

    def test_404(self):
        res = self.client.get(reverse('reviewers.performance', args=['poop']))
        eq_(res.status_code, 404)

    def test_with_email(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        eq_(res.context['profile'].id, self.user.id)

    def test_without_email(self):
        res = self.client.get(reverse('reviewers.performance'))
        eq_(res.status_code, 200)
        eq_(res.context['profile'].id, self.user.id)

    def test_no_reviews(self):
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        assert u'No review points awarded yet' in res.content


class TestQueueSort(AppReviewerTest):

    def setUp(self):
        super(TestQueueSort, self).setUp()
        """Create and set up apps for some filtering fun."""
        self.apps = [app_factory(name='Lillard',
                                 status=mkt.STATUS_PENDING,
                                 is_packaged=False,
                                 version_kw={'version': '1.0'},
                                 file_kw={'status': mkt.STATUS_PENDING},
                                 premium_type=mkt.ADDON_FREE),
                     app_factory(name='Batum',
                                 status=mkt.STATUS_PENDING,
                                 is_packaged=True,
                                 version_kw={'version': '1.0',
                                             'has_editor_comment': True,
                                             'has_info_request': True},
                                 file_kw={'status': mkt.STATUS_PENDING},
                                 premium_type=mkt.ADDON_PREMIUM)]

        # Set up app attributes.
        self.apps[0].update(created=self.days_ago(2))
        self.apps[1].update(created=self.days_ago(5))
        self.apps[0].addonuser_set.create(user=user_factory(email='XXX'))
        self.apps[1].addonuser_set.create(user=user_factory(email='illmatic'))
        self.apps[0].addondevicetype_set.create(
            device_type=mkt.DEVICE_DESKTOP.id)
        self.apps[1].addondevicetype_set.create(
            device_type=mkt.DEVICE_MOBILE.id)

        self.url = reverse('reviewers.apps.queue_pending')

    def test_do_sort_webapp(self):
        """
        Test that apps are sorted in order specified in GET params.
        """
        rf = RequestFactory()
        qs = Webapp.objects.all()

        # Test apps are sorted by created/asc by default.
        req = rf.get(self.url, {'sort': 'invalidsort', 'order': 'dontcare'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[1], self.apps[0]])

        # Test sorting by created, descending.
        req = rf.get(self.url, {'sort': 'created', 'order': 'desc'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[0], self.apps[1]])

        # Test sorting by app name.
        req = rf.get(self.url, {'sort': 'name', 'order': 'asc'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[1], self.apps[0]])

        req = rf.get(self.url, {'sort': 'name', 'order': 'desc'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[0], self.apps[1]])

    def test_do_sort_version_nom(self):
        """Tests version nomination sort order."""
        url = reverse('reviewers.apps.queue_pending')
        user = UserProfile.objects.get(email='editor@mozilla.com')

        version_0 = self.apps[0].versions.get()
        version_0.update(nomination=days_ago(1))
        version_1 = self.apps[1].versions.get()
        version_1.update(nomination=days_ago(2))

        # Throw in some disabled versions, they shouldn't affect order.
        version_factory({'status': mkt.STATUS_DISABLED}, addon=self.apps[0],
                        nomination=days_ago(10))
        version_factory({'status': mkt.STATUS_DISABLED}, addon=self.apps[1],
                        nomination=days_ago(1))
        version_factory({'status': mkt.STATUS_DISABLED}, addon=self.apps[1],
                        nomination=days_ago(20))

        req = mkt.site.tests.req_factory_factory(
            url, user=user, data={'sort': 'nomination'})
        res = queue_apps(req)
        doc = pq(res.content)
        # Desktop and mobile (hidden on desktop) alternate, so we jump by 2.
        eq_(doc('tbody tr')[0].get('data-addon'), str(version_1.addon.id))
        eq_(doc('tbody tr')[2].get('data-addon'), str(version_0.addon.id))

        req = mkt.site.tests.req_factory_factory(
            url, user=user, data={'sort': 'nomination', 'order': 'desc'})
        res = queue_apps(req)
        doc = pq(res.content)
        # Desktop and mobile (hidden on desktop) alternate, so we jump by 2.
        eq_(doc('tbody tr')[0].get('data-addon'), str(version_0.addon.id))
        eq_(doc('tbody tr')[2].get('data-addon'), str(version_1.addon.id))

    def test_do_sort_queue_object(self):
        """Tests sorting queue object."""
        rf = RequestFactory()
        url = reverse('reviewers.apps.queue_rereview')

        earlier_rrq = RereviewQueue.objects.create(addon=self.apps[0])
        later_rrq = RereviewQueue.objects.create(addon=self.apps[1])
        later_rrq.created += timedelta(days=1)
        later_rrq.save()

        request = rf.get(url, {'sort': 'created'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())

        # Assert the order that RereviewQueue objects were created is
        # maintained.
        eq_([earlier_rrq.addon, later_rrq.addon], list(apps))

        request = rf.get(url, {'sort': 'created', 'order': 'desc'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())
        eq_([later_rrq.addon, earlier_rrq.addon], list(apps))

        request = rf.get(url, {'sort': 'name', 'order': 'asc'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())
        eq_([later_rrq.addon, earlier_rrq.addon], list(apps))

        request = rf.get(url, {'sort': 'name', 'order': 'desc'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())
        eq_([earlier_rrq.addon, later_rrq.addon], list(apps))

    def test_sort_with_priority_review(self):
        """Tests the sorts are correct with a priority review flagged app."""

        # Set up the priority review flagged app.
        self.apps.append(app_factory(name='Foxkeh',
                                     status=mkt.STATUS_PENDING,
                                     is_packaged=False,
                                     version_kw={'version': '1.0'},
                                     file_kw={'status': mkt.STATUS_PENDING},
                                     premium_type=mkt.ADDON_FREE,
                                     priority_review=True))

        # Set up app attributes.
        self.apps[2].update(created=self.days_ago(1))
        self.apps[2].addonuser_set.create(
            user=user_factory(email='redpanda@mozilla.com'))
        self.apps[2].addondevicetype_set.create(
            device_type=mkt.DEVICE_DESKTOP.id)

        # And check it also comes out top of waiting time with Webapp model.
        rf = RequestFactory()
        qs = Webapp.objects.all()

        # Test apps are sorted by created/asc by default.
        req = rf.get(self.url, {'sort': 'invalidsort', 'order': 'dontcare'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[2], self.apps[1], self.apps[0]])

        # Test sorting by created, descending.
        req = rf.get(self.url, {'sort': 'created', 'order': 'desc'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs)
        eq_(list(sorted_qs), [self.apps[2], self.apps[0], self.apps[1]])

        # And with Version model.
        version_0 = self.apps[0].versions.get()
        version_0.update(nomination=days_ago(1))
        version_1 = self.apps[1].versions.get()
        version_1.update(nomination=days_ago(2))

        qs = (Version.objects.filter(
              files__status=mkt.STATUS_PENDING,
              addon__disabled_by_user=False,
              addon__status=mkt.STATUS_PENDING)
              .order_by('nomination', 'created')
              .select_related('addon', 'files').no_transforms())

        req = rf.get(self.url, {'sort': 'nomination'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs, date_sort='nomination')
        eq_(list(sorted_qs), [self.apps[2], self.apps[1], self.apps[0]])

        req = rf.get(self.url, {'sort': 'nomination', 'order': 'desc'})
        sorted_qs = ReviewersQueuesHelper(req).sort(qs, date_sort='nomination')
        eq_(list(sorted_qs), [self.apps[2], self.apps[0], self.apps[1]])

        # And with Rereview model.
        url = reverse('reviewers.apps.queue_rereview')

        earlier_rrq = RereviewQueue.objects.create(addon=self.apps[0])
        earlier_rrq.created += timedelta(days=1)
        earlier_rrq.save()
        later_rrq = RereviewQueue.objects.create(addon=self.apps[1])
        later_rrq.created += timedelta(days=2)
        later_rrq.save()
        pri_rrq = RereviewQueue.objects.create(addon=self.apps[2])
        pri_rrq.save()

        request = rf.get(url, {'sort': 'created'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())
        eq_([pri_rrq.addon, earlier_rrq.addon, later_rrq.addon], list(apps))

        request = rf.get(url, {'sort': 'created', 'order': 'desc'})
        apps = ReviewersQueuesHelper(request).sort(RereviewQueue.objects.all())
        eq_([pri_rrq.addon, later_rrq.addon, earlier_rrq.addon], list(apps))


class TestAppsReviewing(AppReviewerTest, AccessMixin):

    def setUp(self):
        super(TestAppsReviewing, self).setUp()
        self.url = reverse('reviewers.apps.apps_reviewing')
        self.apps = [app_factory(name='Antelope',
                                 status=mkt.STATUS_PENDING),
                     app_factory(name='Bear',
                                 status=mkt.STATUS_PENDING),
                     app_factory(name='Cougar',
                                 status=mkt.STATUS_PENDING)]

    def _view_app(self, app_id):
        self.client.post(reverse('reviewers.review_viewing'), {
            'addon_id': app_id})

    def test_no_apps_reviewing(self):
        res = self.client.get(self.url)
        eq_(len(res.context['apps']), 0)

    def test_apps_reviewing(self):
        self._view_app(self.apps[0].id)
        res = self.client.get(self.url)
        eq_(len(res.context['apps']), 1)

    def test_multiple_reviewers_no_cross_streams(self):
        self._view_app(self.apps[0].id)
        self._view_app(self.apps[1].id)
        res = self.client.get(self.url)
        eq_(len(res.context['apps']), 2)

        # Now view an app as another user and verify app.
        self.login('admin@mozilla.com')
        self._view_app(self.apps[2].id)
        res = self.client.get(self.url)
        eq_(len(res.context['apps']), 1)

        # Check original user again to make sure app list didn't increment.
        self.login_as_editor()
        res = self.client.get(self.url)
        eq_(len(res.context['apps']), 2)


class TestLeaderboard(AppReviewerTest):

    def setUp(self):
        super(TestLeaderboard, self).setUp()
        self.url = reverse('reviewers.leaderboard')
        mkt.set_user(self.reviewer_user)

    def _award_points(self, user, score):
        ReviewerScore.objects.create(user=user, note_key=mkt.REVIEWED_MANUAL,
                                     score=score, note='Thing.')

    def test_leaderboard_ranks(self):
        users = (self.reviewer_user,
                 self.regular_user,
                 user_factory(email='clouserw'))

        self._award_points(users[0], mkt.REVIEWED_LEVELS[0]['points'] - 1)
        self._award_points(users[1], mkt.REVIEWED_LEVELS[0]['points'] + 1)
        self._award_points(users[2], mkt.REVIEWED_LEVELS[0]['points'] + 2)

        def get_cells():
            doc = pq(self.client.get(self.url).content.decode('utf-8'))

            cells = doc('#leaderboard > tbody > tr > .name, '
                        '#leaderboard > tbody > tr > .level')

            return [cells.eq(i).text() for i in range(0, cells.length)]

        eq_(get_cells(),
            [users[2].display_name,
             users[1].display_name,
             mkt.REVIEWED_LEVELS[0]['name'],
             users[0].display_name])

        self._award_points(users[0], 1)

        eq_(get_cells(),
            [users[2].display_name,
             users[1].display_name,
             users[0].display_name,
             mkt.REVIEWED_LEVELS[0]['name']])

        self._award_points(users[0], -1)
        self._award_points(users[2], (mkt.REVIEWED_LEVELS[1]['points'] -
                                      mkt.REVIEWED_LEVELS[0]['points']))

        eq_(get_cells(),
            [users[2].display_name,
             mkt.REVIEWED_LEVELS[1]['name'],
             users[1].display_name,
             mkt.REVIEWED_LEVELS[0]['name'],
             users[0].display_name])


class TestReviewPage(mkt.site.tests.TestCase):

    def setUp(self):
        super(TestReviewPage, self).setUp()
        self.app = app_factory(status=mkt.STATUS_PENDING)
        self.reviewer = user_factory(email='editor')
        self.grant_permission(self.reviewer, 'Apps:Review')
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])

    def test_iarc_ratingless_disable_approve_btn(self):
        self.app.update(status=mkt.STATUS_NULL)
        req = req_factory_factory(self.url, user=self.reviewer)
        res = app_review(req, app_slug=self.app.app_slug)
        doc = pq(res.content)
        assert (doc('#review-actions input[value=public]')
                .parents('li').hasClass('disabled'))
        assert not (doc('#review-actions input[value=reject]')
                    .parents('li').hasClass('disabled'))

    def test_iarc_content_ratings(self):
        for body in [mkt.ratingsbodies.CLASSIND.id, mkt.ratingsbodies.USK.id]:
            self.app.content_ratings.create(ratings_body=body, rating=0)
        req = req_factory_factory(self.url, user=self.reviewer)
        res = app_review(req, app_slug=self.app.app_slug)
        doc = pq(res.content)
        eq_(doc('.reviewers-desktop .content-rating').length, 2)
        eq_(doc('.reviewers-mobile .content-rating').length, 2)


class TestAbusePage(AppReviewerTest):

    def setUp(self):
        super(TestAbusePage, self).setUp()
        self.app = app_factory(name=u'My app é <script>alert(5)</script>')
        self.url = reverse('reviewers.apps.review.abuse',
                           args=[self.app.app_slug])
        AbuseReport.objects.create(addon=self.app, message=self.app.name)

    def testXSS(self):
        from django.utils.encoding import smart_unicode
        from jinja2.utils import escape
        content = smart_unicode(self.client.get(self.url).content)
        ok_(not unicode(self.app.name) in content)
        ok_(unicode(escape(self.app.name)) in content)


class TestReviewTranslate(RestOAuth):

    def setUp(self):
        super(TestReviewTranslate, self).setUp()
        self.grant_permission(self.profile, 'Apps:ModerateReview')
        self.create_switch('reviews-translate')
        user = user_factory(email='diego')
        app = app_factory(app_slug='myapp~-_')
        self.review = app.reviews.create(title=u'yes', body=u'oui',
                                         addon=app, user=user,
                                         editorreview=True, rating=4)

    def test_regular_call(self):
        res = self.client.get(reverse('reviewers.review_translate',
                                      args=[self.review.addon.app_slug,
                                            self.review.id, 'fr']))
        self.assert3xx(res, 'https://translate.google.com/#auto/fr/oui', 302)

    @mock.patch('mkt.reviewers.views.requests')
    def test_ajax_call(self, requests):
        # Mock requests.
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            u'data': {
                u'translations': [{
                    u'translatedText': u'oui',
                    u'detectedSourceLanguage': u'fr'
                }]
            }
        }
        requests.get.return_value = response

        # Call translation.
        review = self.review
        url = reverse('reviewers.review_translate',
                      args=[review.addon.app_slug, review.id, 'fr'])
        res = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        eq_(res.status_code, 200)
        eq_(res.content, '{"body": "oui", "title": "oui"}')

    @mock.patch('mkt.reviewers.views.requests')
    def test_invalid_api_key(self, requests):
        # Mock requests.
        response = mock.Mock(status_code=400)
        response.json.return_value = {
            'error': {
                'code': 400,
                'errors': [
                    {'domain': 'usageLimits',
                     'message': 'Bad Request',
                     'reason': 'keyInvalid'}
                ],
                'message': 'Bad Request'
            }
        }
        requests.get.return_value = response

        # Call translation.
        review = self.review
        res = self.client.get(
            reverse('reviewers.review_translate',
                    args=[review.addon.app_slug, review.id, 'fr']),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        eq_(res.status_code, 400)


class TestAdditionalReviewListingAccess(mkt.site.tests.TestCase):

    def setUp(self):
        super(TestAdditionalReviewListingAccess, self).setUp()
        self.user = user_factory()
        self.login(self.user)

    def url(self):
        return reverse('reviewers.apps.additional_review', args=[QUEUE_TARAKO])

    def listing(self):
        return self.client.get(self.url())

    def test_regular_user_has_no_access(self):
        eq_(self.listing().status_code, 403)

    def test_regular_reviewer_has_no_access(self):
        self.grant_permission(self.user, 'Apps:Review')
        eq_(self.listing().status_code, 403)

    def test_tarako_reviewer_has_access(self):
        self.grant_permission(self.user, 'Apps:ReviewTarako')
        eq_(self.listing().status_code, 200)


class TestReviewHistory(mkt.site.tests.TestCase, CommTestMixin):

    def setUp(self):
        super(TestReviewHistory, self).setUp()
        self.app = self.addon = app_factory()
        self.url = reverse('reviewers.apps.review', args=[self.app.app_slug])
        self.grant_permission(user_factory(email='editor'), 'Apps:Review')
        self.login('editor@mozilla.com')
        self._thread_factory()

    def test_comm_url(self):
        r = self.client.get(self.url)
        doc = pq(r.content)
        eq_(doc('#history .item-history').attr('data-comm-app-url'),
            reverse('api-v2:comm-app-list', args=[self.addon.app_slug]) +
            '?limit=1&serializer=simple')

    def test_comm_url_multiple_thread(self):
        self._thread_factory()
        r = self.client.get(self.url)
        doc = pq(r.content)
        eq_(doc('#history .item-history').attr('data-comm-app-url'),
            reverse('api-v2:comm-app-list', args=[self.addon.app_slug]) +
            '?limit=2&serializer=simple')

    def test_comm_url_no_encode(self):
        self.addon = app_factory(app_slug='&#21488;&#21271;')
        self._thread_factory()
        url = reverse('reviewers.apps.review', args=[self.addon.app_slug])
        r = self.client.get(url)
        doc = pq(r.content)
        eq_(doc('#history .item-history').attr('data-comm-app-url'),
            reverse('api-v2:comm-app-list', args=[self.addon.app_slug]) +
            '?limit=1&serializer=simple')


class ModerateLogTest(mkt.site.tests.TestCase):

    def setUp(self):
        super(ModerateLogTest, self).setUp()
        self.review = Review.objects.create(addon=app_factory(), body='body',
                                            user=user_factory(), rating=4,
                                            editorreview=True)
        self.moderator_user = user_factory(email='moderator')
        self.grant_permission(self.moderator_user, 'Apps:ModerateReview')
        mkt.set_user(self.moderator_user)
        self.login(self.moderator_user)

        self.admin_user = user_factory(email='admin')
        self.grant_permission(self.admin_user, '*:*')
        user_factory(email='regular')


class TestModerateLog(ModerateLogTest, AccessMixin):

    def setUp(self):
        super(TestModerateLog, self).setUp()
        self.url = reverse('reviewers.apps.moderatelog')

    def test_log(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)

    def test_start_filter(self):
        r = self.client.get(self.url, dict(start='2011-01-01'))
        eq_(r.status_code, 200)

    def test_enddate_filter(self):
        """
        Make sure that if our end date is 1/1/2011, that we include items from
        1/1/2011.
        """
        mkt.log(mkt.LOG.APPROVE_REVIEW, self.review, self.review.addon,
                created=datetime(2011, 1, 1))

        r = self.client.get(self.url, dict(end='2011-01-01'))
        eq_(r.status_code, 200)
        eq_(pq(r.content)('tbody td').eq(0).text(), 'Jan 1, 2011, 12:00:00 AM')

    def test_action_filter(self):
        """
        Based on setup we should see only two items if we filter for deleted
        reviews.
        """
        for i in xrange(2):
            mkt.log(mkt.LOG.APPROVE_REVIEW, self.review.addon, self.review)
            mkt.log(mkt.LOG.DELETE_REVIEW, self.review.addon, self.review)
        r = self.client.get(self.url, dict(search='deleted'))
        eq_(pq(r.content)('tbody tr').length, 2)

    def test_no_results(self):
        r = self.client.get(self.url, dict(end='2004-01-01'))
        no_results = 'No events found for this period.'
        assert no_results in r.content, 'Expected no results to be found.'

    def test_display_name_xss(self):
        mkt.log(mkt.LOG.APPROVE_REVIEW, self.review, self.review.addon,
                user=self.admin_user)
        self.admin_user.display_name = '<script>alert("xss")</script>'
        self.admin_user.save()
        assert '<script>' in self.admin_user.display_name, (
            'Expected <script> to be in display name')
        r = self.client.get(self.url)
        pq(r.content)('#log-listing tbody td').eq(1).html()
        assert '<script>' not in r.content
        assert '&lt;script&gt;' in r.content


class TestModerateLogDetail(ModerateLogTest, AccessMixin):

    def setUp(self):
        super(TestModerateLogDetail, self).setUp()
        # AccessMixin needs a url property.
        self.url = self._url(0)

    def _url(self, id):
        return reverse('reviewers.apps.moderatelog.detail', args=[id])

    def test_detail_page(self):
        mkt.log(mkt.LOG.APPROVE_REVIEW, self.review.addon, self.review)
        e_id = ActivityLog.objects.editor_events()[0].id
        r = self.client.get(self._url(e_id))
        eq_(r.status_code, 200)

    def test_undelete_selfmoderation(self):
        e_id = mkt.log(
            mkt.LOG.DELETE_REVIEW, self.review.addon, self.review).id
        self.review.delete()
        r = self.client.post(self._url(e_id), {'action': 'undelete'})
        eq_(r.status_code, 302)
        self.review = Review.objects.get(id=self.review.id)
        assert not self.review.deleted, 'Review should be undeleted now.'

    def test_undelete_admin(self):
        e_id = mkt.log(
            mkt.LOG.DELETE_REVIEW, self.review.addon, self.review).id
        self.review.delete()
        self.client.logout()
        self.login(self.admin_user)
        r = self.client.post(self._url(e_id), {'action': 'undelete'})
        eq_(r.status_code, 302)
        self.review = Review.objects.get(id=self.review.id)
        assert not self.review.deleted, 'Review should be undeleted now.'

    def test_undelete_unauthorized(self):
        # Delete as admin (or any other user than the reviewer).
        e_id = mkt.log(mkt.LOG.DELETE_REVIEW, self.review.addon, self.review,
                       user=self.admin_user).id
        self.review.delete()
        # Try to undelete as normal reviewer.
        r = self.client.post(self._url(e_id), {'action': 'undelete'})
        eq_(r.status_code, 403)
        self.review = Review.with_deleted.get(id=self.review.id)
        assert self.review.deleted, 'Review shouldn`t have been undeleted.'
