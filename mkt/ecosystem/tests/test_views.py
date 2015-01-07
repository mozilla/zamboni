from django.core.urlresolvers import reverse

import basket
import mock
from nose.tools import eq_
from pyquery import PyQuery as pq

import mkt.site.tests

from mkt.ecosystem.urls import APP_SLUGS


VIEW_PAGES = (
    'partners', 'support'
)

REDIRECT_PAGES = (
    'app_manager', 'build_app_generator', 'build_apps_offline',
    'build_dev_tools', 'build_ffos', 'build_game_apps', 'build_intro',
    'build_manifests', 'build_mobile_developers', 'build_payments',
    'build_quick', 'build_reference', 'build_tools', 'build_web_developers',
    'design_concept', 'design_fundamentals', 'design_patterns', 'design_ui',
    'dev_phone', 'ffos_guideline', 'firefox_os_simulator', 'publish_deploy',
    'publish_hosted', 'publish_packaged', 'publish_payments', 'publish_review',
    'publish_submit', 'responsive_design'
)


class TestLanding(mkt.site.tests.TestCase):

    def setUp(self):
        self.url = reverse('ecosystem.landing')

    def test_legacy_redirect(self):
        r = self.client.get('/ecosystem/')
        self.assert3xx(r, '/developers/', 301)

    def test_tutorials_default(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'ecosystem/landing.html')

    @mock.patch('basket.subscribe')
    def test_newsletter_form_valid(self, subscribe_mock):
        d = {'email': 'a@b.cd', 'email_format': 'T', 'privacy': True,
             'country': 'us'}
        r = self.client.post(self.url, d)
        self.assert3xx(r, reverse('ecosystem.landing'))
        assert subscribe_mock.called

    @mock.patch('basket.subscribe')
    def test_newsletter_form_invalid(self, subscribe_mock):
        d = {'email': '', 'email_format': 'T', 'privacy': True,
             'country': 'us'}
        r = self.client.post(self.url, d)
        eq_(r.status_code, 200)
        self.assertFormError(r, 'newsletter_form', 'email',
                             [u'Please enter a valid email address.'])
        assert not subscribe_mock.called

    @mock.patch('basket.subscribe')
    def test_newsletter_form_exception(self, subscribe_mock):
        subscribe_mock.side_effect = basket.BasketException
        d = {'email': 'a@b.cd', 'email_format': 'T', 'privacy': True,
             'country': 'us'}
        r = self.client.post(self.url, d)
        eq_(r.status_code, 200)
        eq_(pq(r.content)('.notification-box.error').text(),
            'We apologize, but an error occurred in our '
            'system. Please try again later.')
        assert subscribe_mock.called


class TestDevHub(mkt.site.tests.TestCase):

    def test_content_pages(self):
        for page in VIEW_PAGES:
            r = self.client.get(reverse('ecosystem.%s' % page))
            eq_(r.status_code, 200, '%s: status %s' % (page, r.status_code))
            self.assertTemplateUsed(r, 'ecosystem/%s.html' % page)

    def test_redirect_pages(self):
        for page in REDIRECT_PAGES:
            r = self.client.get(reverse('ecosystem.%s' % page))
            eq_(r.status_code, 301, '%s: status %s' % (page, r.status_code))

    def test_app_redirect_pages(self):
        mdn_url = (
            'https://developer.mozilla.org/docs/Web/Apps/Reference_apps/')
        for mkt_slug, mdn_slug in APP_SLUGS.iteritems():
            r = self.client.get(reverse('ecosystem.apps_documentation',
                                        args=[mkt_slug]))
            self.assert3xx(r, mdn_url + mdn_slug, status_code=301)

        r = self.client.get(reverse('ecosystem.apps_documentation',
                                    args=['badslug']))
        self.assert3xx(r, mdn_url, status_code=301)
