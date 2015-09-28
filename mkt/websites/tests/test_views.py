import json

from django.core.urlresolvers import reverse
from django.db import transaction

import responses
from nose.tools import eq_, ok_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.applications import DEVICE_DESKTOP
from mkt.constants.base import CONTENT_ICON_SIZES, STATUS_PENDING
from mkt.constants.regions import URY, USA
from mkt.site.fixtures import fixture
from mkt.site.tests import ESTestCase, TestCase
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.websites.models import Website, WebsiteSubmission
from mkt.websites.utils import website_factory
from mkt.websites.views import WebsiteMetadataScraperView


class TestWebsiteESView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.website = website_factory(**{
            'title': 'something',
            'categories': ['books-comics', 'sports'],
            # Preferred_regions and devices are stored as a json array of ids.
            'devices': [DEVICE_DESKTOP.id],
            'preferred_regions': [URY.id, USA.id],
            'icon_type': 'image/png',
            'icon_hash': 'fakehash',
        })
        self.category = 'books-comics'
        self.url = reverse('api-v2:website-search-api')
        super(TestWebsiteESView, self).setUp()
        self.refresh('website')

    def tearDown(self):
        Website.get_indexer().unindexer(_all=True)
        super(TestWebsiteESView, self).tearDown()

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_basic(self):
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 1)
        data = response.json['objects'][0]
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['name'], {'en-US': self.website.name})
        eq_(data['short_name'], {'en-US': self.website.short_name})
        eq_(data['url'], self.website.url)
        eq_(data['mobile_url'], self.website.mobile_url)
        eq_(data['categories'], ['books-comics', 'sports'])
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['device_types'], ['desktop']),
        eq_(data['icons']['128'], self.website.get_icon_url(128))
        ok_(data['icons']['128'].endswith('?modified=fakehash'))
        eq_(sorted(int(k) for k in data['icons'].keys()), CONTENT_ICON_SIZES)
        eq_(data['name'], {'en-US': self.website.name})
        eq_(data['short_name'], {'en-US': self.website.short_name})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['url'], self.website.url)

    def test_list(self):
        self.website2 = website_factory(url='http://www.lol.com/')
        self.refresh('website')
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)

    def test_wrong_category(self):
        with transaction.atomic():
            res = self.anon.get(self.url, data={'cat': self.category + 'xq'})
            eq_(res.status_code, 400)
            eq_(res['Content-Type'], 'application/json; charset=utf-8')

    def test_right_category_but_not_present(self):
        self.category = 'travel'
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        eq_(res.json['objects'], [])

    def test_right_category_present(self):
        res = self.anon.get(self.url, data={'cat': self.category})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_region_preference(self):
        # Websites don't have region exclusions, only "preferred" regions.
        res = self.anon.get(self.url, data={'region': 'br'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

        res = self.anon.get(self.url, data={'region': 'us'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

    def test_q(self):
        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        obj = res.json['objects'][0]
        eq_(obj['id'], self.website.pk)

    def test_q_relevancy(self):
        # Add 2 websites - the last one has 'something' appearing in both its
        # title and its description, so it should be booster and appear higher
        # in the results.
        website_factory(title='something')
        boosted_website = website_factory(title='something',
                                          description='something')
        self.reindex(Website)

        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 3)
        obj = res.json['objects'][0]
        eq_(obj['id'], boosted_website.pk)

    def test_q_relevancy_region(self):
        # Add another website without any preferred regions: it should rank
        # higher without region (description increases its score), lower with
        # one (region preference increases the score for the initial website).
        self.website2 = website_factory(title='something',
                                        description='something')
        self.reindex(Website)
        res = self.anon.get(self.url, data={'q': 'something'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 2)
        eq_(objs[0]['id'], self.website2.pk)
        eq_(objs[1]['id'], self.website.pk)

        res = self.anon.get(self.url, data={'q': 'something', 'region': 'us'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 2)
        eq_(objs[0]['id'], self.website.pk)
        eq_(objs[1]['id'], self.website2.pk)

    def test_device_not_present(self):
        res = self.anon.get(
            self.url, data={'dev': 'android', 'device': 'tablet'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

    def test_device_present(self):
        res = self.anon.get(self.url, data={'dev': 'desktop'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)

    def test_keywords(self):
        website_factory()
        self.website.keywords.add(Tag.objects.create(tag_text='hodor'))
        self.website.keywords.add(Tag.objects.create(tag_text='radar'))
        self.website.save()
        self.refresh('website')
        res = self.anon.get(self.url, data={'q': 'hodor'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)
        eq_(sorted(objs[0]['keywords']), sorted(['hodor', 'radar']))


class TestWebsiteView(RestOAuth, TestCase):
    def setUp(self):
        super(TestWebsiteView, self).setUp()
        self.website = website_factory(**{
            'categories': ['books-comics', 'sports'],
            # Preferred_regions and devices are stored as a json array of ids.
            'devices': [DEVICE_DESKTOP.id],
            'preferred_regions': [URY.id, USA.id],
            'icon_type': 'image/png',
            'icon_hash': 'fakehash',
        })
        self.url = reverse('api-v2:website-detail',
                           kwargs={'pk': self.website.pk})

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_basic(self):
        response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        data = response.json
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['name'], {'en-US': self.website.name})
        eq_(data['short_name'], {'en-US': self.website.short_name})
        eq_(data['url'], self.website.url)
        eq_(data['mobile_url'], self.website.mobile_url)
        eq_(data['categories'], ['books-comics', 'sports'])
        eq_(data['description'], {'en-US': self.website.description})
        eq_(data['device_types'], ['desktop']),
        eq_(data['icons']['128'], self.website.get_icon_url(128))
        ok_(data['icons']['128'].endswith('?modified=fakehash'))
        eq_(sorted(int(k) for k in data['icons'].keys()), CONTENT_ICON_SIZES)
        eq_(data['name'], {'en-US': self.website.name})
        eq_(data['short_name'], {'en-US': self.website.short_name})
        eq_(data['title'], {'en-US': self.website.title})
        eq_(data['url'], self.website.url)

    def test_disabled(self):
        self.website.update(is_disabled=True)
        response = self.anon.get(self.url)
        eq_(response.status_code, 404)

    def test_wrong_status(self):
        self.website.update(status=STATUS_PENDING)
        response = self.anon.get(self.url)
        eq_(response.status_code, 404)


class TestReviewerSearch(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.website = website_factory(**{
            'title': 'something',
            'categories': json.dumps(['books-comics', 'sports']),
            'status': STATUS_PENDING,
        })
        self.url = reverse('api-v2:reviewers-website-search-api')
        self.user = UserProfile.objects.get(pk=2519)
        self.grant_permission(self.user, 'Apps:Review')
        super(TestReviewerSearch, self).setUp()
        self.refresh('website')

    def tearDown(self):
        Website.get_indexer().unindexer(_all=True)
        super(TestReviewerSearch, self).tearDown()

    def test_access(self):
        with transaction.atomic():
            eq_(self.anon.get(self.url).status_code, 403)
        self.remove_permission(self.user, 'Apps:Review')
        with transaction.atomic():
            eq_(self.client.get(self.url).status_code, 403)

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get')

    def test_status_filtering(self):
        res = self.client.get(self.url, data={'status': 'public'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 0)
        res = self.client.get(self.url, data={'status': 'pending'})
        eq_(res.status_code, 200)
        objs = res.json['objects']
        eq_(len(objs), 1)


class TestWebsiteScrape(RestOAuth, TestCase):
    def setUp(self):
        self.url = reverse('api-v2:website-scrape')
        super(TestWebsiteScrape, self).setUp()

    def go(self, url=None):
        qs = {}
        if url:
            qs = {'url': url}
        response = self.anon.get(self.url, qs)
        return response, json.loads(response.content)

    def test_no_url(self):
        response, content = self.go()
        eq_(response.status_code, 400)
        eq_(content, WebsiteMetadataScraperView.errors['no_url'])

    @responses.activate
    def test_site_404(self):
        URL = 'https://marketplace.firefox.com/'
        responses.add(responses.GET, URL, status=404)
        response, content = self.go(url=URL)
        eq_(response.status_code, 400)
        eq_(content, WebsiteMetadataScraperView.errors['network'])

    @responses.activate
    def test_site_500(self):
        URL = 'https://marketplace.firefox.com/'
        responses.add(responses.GET, URL, status=500)
        response, content = self.go(url=URL)
        eq_(response.status_code, 400)
        eq_(content, WebsiteMetadataScraperView.errors['network'])

    @responses.activate
    def test_empty_body(self):
        URL = 'https://marketplace.firefox.com/'
        responses.add(responses.GET, URL, '', status=200)
        response, content = self.go(url=URL)
        eq_(response.status_code, 400)
        eq_(content, WebsiteMetadataScraperView.errors['malformed_data'])

    @responses.activate
    def test_valid(self):
        URL = 'https://marketplace.firefox.com/'
        responses.add(responses.GET, URL, '<html />', status=200)
        response, content = self.go(url=URL)
        eq_(response.status_code, 200)

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.client.get(self.url), 'get')


class TestWebsiteSubmissionViewSetCreate(RestOAuth, TestCase):
    def setUp(self):
        self.url = reverse('api-v2:website-submit')
        self.data = {
            'canonical_url': 'https://www.bro.app',
            'categories': ['lifestyle', 'music'],
            'detected_icon': 'https://www.bro.app/apple-touch.png',
            'description': 'We cannot tell you what a Bro is. But bros know.',
            'keywords': ['social networking', 'Gilfoyle', 'Silicon Valley'],
            'name': 'Bro',
            'preferred_regions': ['us', 'ca', 'fr'],
            'public_credit': False,
            'url': 'https://m.bro.app',
            'why_relevant': 'Ummm...bro. You know.',
            'works_well': 3
        }
        super(TestWebsiteSubmissionViewSetCreate, self).setUp()

    def go(self, anon=False):
        client = self.client
        if anon:
            client = self.anon
        response = client.post(self.url, json.dumps(self.data))
        return response, json.loads(response.content)

    def compare_values(self, content):
        ok_('id' in content)
        eq_(content['canonical_url'], self.data['canonical_url'])
        eq_(content['categories'], self.data['categories'])
        eq_(content['detected_icon'], self.data['detected_icon'])
        eq_(content['keywords'], self.data['keywords'])
        eq_(content['preferred_regions'], self.data['preferred_regions'])
        eq_(content['public_credit'], self.data['public_credit'])
        eq_(content['url'], self.data['url'])
        eq_(content['why_relevant'], self.data['why_relevant'])
        eq_(content['works_well'], self.data['works_well'])
        ok_(self.data['description'] in content['description'].values())
        ok_(self.data['name'] in content['name'].values())

    def missing_field(self, field_name, failure=True):
        self.data[field_name] = None
        response, content = self.go()
        eq_(response.status_code, 400 if failure else 201)
        return response, content

    def test_get(self):
        self.grant_permission(self.user, 'Websites:Submit')
        response = self.client.get(self.url)
        eq_(response.status_code, 405)

    def test_get_no_perms(self):
        response = self.client.get(self.url)
        eq_(response.status_code, 403)

    def test_post(self):
        self.grant_permission(self.user, 'Websites:Submit')
        response, content = self.go()
        eq_(response.status_code, 201)
        self.compare_values(content)
        eq_(WebsiteSubmission.objects.all()[0].submitter, self.user)

    def test_post_no_perms(self):
        response, content = self.go()
        eq_(response.status_code, 403)

    def test_post_anon(self):
        response, content = self.go(anon=True)
        eq_(response.status_code, 403)

    def test_allow_empty_preferred_regions(self):
        self.grant_permission(self.user, 'Websites:Submit')
        self.data['preferred_regions'] = []
        response, content = self.go()
        eq_(response.status_code, 201)
        eq_(content['preferred_regions'], [])


class TestWebsiteSubmissionViewSetList(RestOAuth, TestCase):
    def setUp(self):
        self.url = reverse('api-v2:website-submissions')
        self.data = {
            'canonical_url': 'https://www.bro.app',
            'categories': ['lifestyle', 'music'],
            'detected_icon': 'https://www.bro.app/apple-touch.png',
            'description': 'We cannot tell you what a Bro is. But bros know.',
            'keywords': ['social networking', 'Gilfoyle', 'Silicon Valley'],
            'name': 'Bro',
            'preferred_regions': ['us', 'ca', 'fr'],
            'public_credit': False,
            'url': 'https://m.bro.app',
            'why_relevant': 'Ummm...bro. You know.',
            'works_well': 3
        }
        super(TestWebsiteSubmissionViewSetList, self).setUp()

    def test_list(self):
        WebsiteSubmission.objects.create(**self.data)
        WebsiteSubmission.objects.create(**self.data)
        self.grant_permission(self.user, 'Websites:Submit')
        response = self.client.get(self.url)
        eq_(response.status_code, 200)
        eq_(response.json['objects'][0]['url'], 'https://m.bro.app')
        eq_(response.json['meta']['total_count'], 2)

    def test_anon(self):
        response = self.client.get(self.url)
        eq_(response.status_code, 403)
