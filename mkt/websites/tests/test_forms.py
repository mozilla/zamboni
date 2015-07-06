# -*- coding: utf-8 -*-
from django.test.client import RequestFactory

from nose.tools import eq_

import mkt
from mkt.constants.applications import DEVICE_DESKTOP, DEVICE_GAIA
from mkt.site.tests import TestCase
from mkt.tags.models import Tag
from mkt.websites.forms import WebsiteForm
from mkt.websites.utils import website_factory


class TestWebsiteForm(TestCase):

    def setUp(self):
        super(TestWebsiteForm, self).setUp()
        self.request = RequestFactory().get('/')
        self.website = website_factory()
        self.website.keywords.add(Tag.objects.create(tag_text='horton'))
        self.data = {
            'title_en-us': unicode(self.website.title),
            'name_en-us': unicode(self.website.name),
            'short_name_en-us': unicode(self.website.short_name),
            'description_en-us': unicode(self.website.description),
            'keywords': 'thing one, thing two',
            'preferred_regions': [1, 2],
            'categories': ['books-comics', 'reference'],
            'devices': [DEVICE_GAIA.id],
            'status': mkt.STATUS_PUBLIC,
            'is_disabled': False,
            'url': self.website.url,
        }

    def test_basic(self):
        data = self.data.copy()
        data.update({
            'title_en-us': u'Tëst',
            'url': u'http://test.com',
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        self.website.reload()
        eq_(unicode(self.website.title), u'Tëst')
        eq_(self.website.url, u'http://test.com/')

    def test_keywords(self):
        data = self.data.copy()
        data.update({
            'keywords': 'thing one, thing two',
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        self.website.reload()
        self.assertSetEqual(
            self.website.keywords.values_list('tag_text', flat=True),
            ['thing one', 'thing two']
        )

    def test_categories(self):
        data = self.data.copy()
        categories = ['news', 'music']
        data.update({
            'categories': categories,
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        self.website.reload()
        self.assertSetEqual(self.website.categories, categories)

    def test_categories_error(self):
        data = self.data.copy()
        categories = ['news', 'music', 'games']
        data.update({
            'categories': categories,
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert not form.is_valid()
        eq_(form.errors['categories'][0], u'You can have only 2 categories.')

    def test_regions(self):
        data = self.data.copy()
        regions = ['1', '2', '8']
        data.update({
            'preferred_regions': regions,
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        self.website.reload()
        self.assertSetEqual(self.website.preferred_regions, map(int, regions))

    def test_devices(self):
        data = self.data.copy()
        devices = [str(DEVICE_DESKTOP.id), str(DEVICE_GAIA.id)]
        data.update({
            'devices': devices,
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        self.website.reload()
        self.assertSetEqual(self.website.devices, map(int, devices))

    def test_l10n(self):
        data = self.data.copy()
        data.update({
            'name_es': 'Spanish name',
            'title_es': 'Spanish title',
            'description_es': 'Spanish description',
        })
        form = WebsiteForm(request=self.request, instance=self.website,
                           data=data)
        assert form.is_valid(), form.errors
        form.save()
        with self.activate('es'):
            self.website.reload()
            eq_(unicode(self.website.name), 'Spanish name')
            eq_(unicode(self.website.title), 'Spanish title')
            eq_(unicode(self.website.description), 'Spanish description')
