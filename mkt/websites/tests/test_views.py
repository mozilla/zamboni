import json

from django.core.urlresolvers import reverse

from nose.tools import eq_, ok_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.constants.base import CONTENT_ICON_SIZES, STATUS_PENDING
from mkt.constants.regions import URY, USA
from mkt.site.fixtures import fixture
from mkt.site.tests import ESTestCase, TestCase
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestWebsiteESView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.website = website_factory(**{
            'title': 'something',
            'categories': json.dumps(['books', 'sports']),
            # Preferred_regions are stored as a json array of ids.
            'preferred_regions': json.dumps([URY.id, USA.id]),
            'icon_type': 'image/png',
            'icon_hash': 'fakehash',
        })
        self.category = 'books'
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
        eq_(data['categories'], ['books', 'sports'])
        eq_(data['icons']['128'], self.website.get_icon_url(128))
        ok_(data['icons']['128'].endswith('?modified=fakehash'))
        eq_(sorted(int(k) for k in data['icons'].keys()), CONTENT_ICON_SIZES)

    def test_list(self):
        self.website2 = website_factory(url='http://www.lol.com/')
        self.refresh('website')
        with self.assertNumQueries(0):
            response = self.anon.get(self.url)
        eq_(response.status_code, 200)
        eq_(len(response.json['objects']), 2)

    def test_wrong_category(self):
        res = self.anon.get(self.url, data={'cat': self.category + 'xq'})
        eq_(res.status_code, 400)
        eq_(res['Content-Type'], 'application/json')

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
        # Websites are marked as compatible with every device.
        res = self.anon.get(
            self.url, data={'dev': 'android', 'device': 'tablet'})
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 1)

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
            'categories': json.dumps(['books', 'sports']),
            # Preferred_regions are stored as a json array of ids.
            'preferred_regions': json.dumps([URY.id, USA.id]),
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
        eq_(data['categories'], ['books', 'sports'])
        eq_(data['icons']['128'], self.website.get_icon_url(128))
        ok_(data['icons']['128'].endswith('?modified=fakehash'))
        eq_(sorted(int(k) for k in data['icons'].keys()), CONTENT_ICON_SIZES)

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
            'categories': json.dumps(['books', 'sports']),
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
        eq_(self.anon.get(self.url).status_code, 403)
        self.remove_permission(self.user, 'Apps:Review')
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
