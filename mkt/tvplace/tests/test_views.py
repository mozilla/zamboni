import json

from django.core.urlresolvers import reverse

from nose.tools import eq_, ok_

import mkt
from mkt.api.tests import BaseAPI
from mkt.api.tests.test_oauth import RestOAuth
from mkt.site.fixtures import fixture
from mkt.site.tests import ESTestCase, app_factory
from mkt.tvplace.serializers import (TVAppSerializer,
                                     TVWebsiteSerializer)
from mkt.webapps.models import Webapp
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


TVPLACE_APP_EXCLUDED_FIELDS = (
    'absolute_url', 'app_type', 'banner_message', 'banner_regions',
    'created', 'default_locale', 'device_types', 'feature_compatibility',
    'is_offline', 'is_packaged', 'payment_account', 'payment_required',
    'premium_type', 'price', 'price_locale', 'regions', 'resource_uri',
    'supported_locales', 'upsell', 'upsold', 'versions')


TVPLACE_WEBSITE_EXCLUDED_FIELDS = ('title', 'mobile_url')


def assert_tvplace_app(data):
    for field in TVPLACE_APP_EXCLUDED_FIELDS:
        ok_(field not in data, field)
    for field in TVAppSerializer.Meta.fields:
        ok_(field in data, field)


def assert_tvplace_website(data):
    for field in TVPLACE_WEBSITE_EXCLUDED_FIELDS:
        ok_(field not in data, field)
    for field in TVWebsiteSerializer.Meta.fields:
        ok_(field in data, field)


class TestAppDetail(BaseAPI):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestAppDetail, self).setUp()
        Webapp.objects.get(pk=337141).addondevicetype_set.create(
            device_type=5)
        self.url = reverse('tv-app-detail', kwargs={'pk': 337141})

    def test_get(self):
        res = self.client.get(self.url)
        data = json.loads(res.content)
        eq_(data['id'], 337141)

    def test_get_slug(self):
        Webapp.objects.get(pk=337141).update(app_slug='foo')
        res = self.client.get(reverse('tv-app-detail',
                                      kwargs={'pk': 'foo'}))
        data = json.loads(res.content)
        eq_(data['id'], 337141)


class TestMultiSearchView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519', 'webapp_337141')

    def test_get_multi(self):
        website = website_factory()
        app = app_factory()
        website_factory(devices=[mkt.DEVICE_DESKTOP.id,
                                 mkt.DEVICE_GAIA.id])
        app.addondevicetype_set.create(device_type=mkt.DEVICE_TV.id)
        self.reindex(Webapp)
        self.reindex(Website)
        self.refresh()
        url = reverse('tv-multi-search-api')
        res = self.client.get(url)
        objects = res.json['objects']
        eq_(len(objects), 2)
        eq_(objects[0]['doc_type'], 'webapp')
        assert_tvplace_app(objects[0])
        eq_(objects[0]['id'], app.pk)

        eq_(objects[1]['doc_type'], 'website')
        assert_tvplace_website(objects[1])
        eq_(objects[1]['id'], website.pk)
