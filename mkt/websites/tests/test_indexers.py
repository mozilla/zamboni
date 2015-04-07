# -*- coding: utf-8 -*-
from nose.tools import eq_, ok_

from mkt.constants.applications import DEVICE_GAIA, DEVICE_DESKTOP
from mkt.constants.regions import BRA, GTM, URY
from mkt.site.tests import TestCase
from mkt.websites.indexers import WebsiteIndexer
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestWebsiteIndexer(TestCase):

    def setUp(self):
        self.indexer = Website.get_indexer()()

    def test_model(self):
        eq_(self.indexer.get_model(), Website)
        ok_(isinstance(self.indexer, WebsiteIndexer))

    def test_get_mapping_ok(self):
        eq_(WebsiteIndexer.get_mapping_type_name(), 'website')
        ok_(isinstance(self.indexer.get_mapping(), dict))

    def test_index(self):
        with self.settings(ES_INDEXES={'website': 'websites'}):
            eq_(WebsiteIndexer.get_index(), 'websites')

    def test_mapping(self):
        mapping = WebsiteIndexer.get_mapping()
        eq_(mapping.keys(), ['website'])
        eq_(mapping['website']['_all'], {'enabled': False})

    def _get_doc(self):
        return self.indexer.extract_document(self.obj.pk, self.obj)

    def test_extract(self):
        self.obj = website_factory(**{
            'categories': ['books', 'sports'],
            # This assumes devices and region_exclusions are stored as a json
            # array of ids, not slugs.
            'devices': [DEVICE_GAIA.id, DEVICE_DESKTOP.id],
            'region_exclusions': [BRA.id, GTM.id, URY.id],
            'icon_type': 'png',
            'icon_hash': 'f4k3h4sh',
        })
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['category'], self.obj.categories)
        eq_(doc['last_updated'], self.obj.last_updated)
        eq_(doc['description'], [unicode(self.obj.description)])
        eq_(doc['description_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.description)}])
        eq_(doc['description_english'], [unicode(self.obj.description)])
        eq_(doc['default_locale'], self.obj.default_locale)
        eq_(doc['icon_hash'], self.obj.icon_hash)
        eq_(doc['icon_type'], self.obj.icon_type)
        eq_(doc['default_locale'], self.obj.default_locale)
        eq_(doc['created'], self.obj.created)
        eq_(doc['modified'], self.obj.modified)
        eq_(doc['url'], [unicode(self.obj.url)])
        eq_(doc['url_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.url)}])
        eq_(doc['short_title'], [unicode(self.obj.short_title)])
        eq_(doc['short_title_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.short_title)}])
        eq_(doc['title'], [unicode(self.obj.title)])
        eq_(doc['title_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.title)}])
        eq_(doc['title_english'], [unicode(self.obj.title)])
        eq_(doc['device'], self.obj.devices)
        eq_(doc['region_exclusions'], self.obj.region_exclusions)

    def test_extract_with_translations(self):
        self.obj = website_factory()
        title = {
            'en-US': u'Site Tîtle',
            'fr': u'Titrè du sïte',
        }
        self.obj.title = title
        self.obj.save()
        doc = self._get_doc()
        eq_(sorted(doc['title']), [title['en-US'], title['fr']])
        eq_(sorted(doc['title_translations']),
            [{'lang': 'en-US', 'string': title['en-US']},
             {'lang': 'fr', 'string': title['fr']}])
        eq_(doc['title_english'], [title['en-US']])
        eq_(doc['title_french'], [title['fr']])
