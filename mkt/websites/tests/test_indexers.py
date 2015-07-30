# -*- coding: utf-8 -*-
from nose.tools import eq_, ok_

from mkt.constants.applications import DEVICE_DESKTOP, DEVICE_GAIA
from mkt.constants.regions import URY, USA
from mkt.search.utils import get_boost
from mkt.site.tests import ESTestCase, TestCase
from mkt.tags.models import Tag
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
            # Preferred_regions and devices are stored as a json array of ids.
            'devices': [DEVICE_GAIA.id, DEVICE_DESKTOP.id],
            'preferred_regions': [URY.id, USA.id],
            'icon_type': 'png',
            'icon_hash': 'f4k3h4sh',
        })
        self.obj.keywords.add(Tag.objects.create(tag_text='hodor'))
        self.obj.keywords.add(Tag.objects.create(tag_text='radar'))
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['category'], self.obj.categories)
        eq_(doc['last_updated'], self.obj.last_updated)
        eq_(doc['description'], [unicode(self.obj.description)])
        eq_(doc['description_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.description)}])
        eq_(doc['description_l10n_english'], [unicode(self.obj.description)])
        eq_(doc['default_locale'], self.obj.default_locale)
        eq_(doc['device'], self.obj.devices)
        eq_(doc['icon_hash'], self.obj.icon_hash)
        eq_(doc['icon_type'], self.obj.icon_type)
        eq_(doc['default_locale'], self.obj.default_locale)
        eq_(doc['created'], self.obj.created)
        eq_(doc['modified'], self.obj.modified)
        eq_(doc['name'], [unicode(self.obj.name)])
        eq_(doc['name_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.name)}])
        eq_(doc['preferred_regions'], self.obj.preferred_regions)
        eq_(doc['promo_img_hash'], self.obj.promo_img_hash)
        eq_(doc['reviewed'], self.obj.last_updated)
        eq_(doc['short_name'], [unicode(self.obj.short_name)])
        eq_(doc['short_name_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.short_name)}])
        eq_(sorted(doc['tags']), sorted(['hodor', 'radar']))
        eq_(doc['title'], [unicode(self.obj.title)])
        eq_(doc['title_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.title)}])
        eq_(doc['url'], self.obj.url)
        eq_(doc['url_tokenized'],
            unicode(self.indexer.strip_url(self.obj.url)))

    def test_extract_with_translations(self):
        self.obj = website_factory()
        title = {
            'en-US': u'Site Tîtle',
            'fr': u'Titrè du sïte',
        }
        self.obj.title = title
        name = {
            'en-US': u'Namé Site',
            'fr': u'Nom du sïte',
        }
        self.obj.name = name
        self.obj.save()
        doc = self._get_doc()

        eq_(sorted(doc['title']), [title['en-US'], title['fr']])
        eq_(sorted(doc['title_translations']),
            [{'lang': 'en-US', 'string': title['en-US']},
             {'lang': 'fr', 'string': title['fr']}])

        eq_(sorted(doc['name']), [name['en-US'], name['fr']])
        eq_(sorted(doc['name_translations']),
            [{'lang': 'en-US', 'string': name['en-US']},
             {'lang': 'fr', 'string': name['fr']}])
        eq_(doc['name_l10n_french'], [name['fr']])
        eq_(doc['name_l10n_english'], [name['en-US']])
        eq_(doc['name_sort'], name['en-US'].lower())

    def test_installs_to_popularity(self):
        self.obj = website_factory()
        # No installs.
        doc = self._get_doc()
        # Boost is multiplied by 4 if it's public.
        eq_(doc['boost'], 1.0 * 4)
        eq_(doc['popularity'], 0)

        # Add some popularity.
        self.obj.popularity.create(region=0, value=50.0)
        # Test an adolescent region.
        self.obj.popularity.create(region=2, value=10.0)
        # Test a mature region.
        self.obj.popularity.create(region=7, value=10.0)

        doc = self._get_doc()
        eq_(doc['boost'], get_boost(self.obj))
        eq_(doc['popularity'], 50)
        eq_(doc['popularity_7'], 10)
        # Adolescent regions popularity value is not stored.
        ok_('popularity_2' not in doc)

    def test_trending(self):
        self.obj = website_factory()
        self.obj.trending.create(region=0, value=10.0)
        # Test an adolescent region.
        self.obj.trending.create(region=2, value=50.0)
        # Test a mature region.
        self.obj.trending.create(region=7, value=50.0)

        doc = self._get_doc()
        eq_(doc['trending'], 10.0)
        eq_(doc['trending_7'], 50.0)

        # Adolescent regions trending value is not stored.
        ok_('trending_2' not in doc)

    def test_url(self):
        self.obj = website_factory()
        expected = {
            'http://domain.com': 'domain',
            'https://www.domain.com': 'domain',
            'http://m.domain.com': 'domain',
            'http://mobile.domain.com': 'domain',
            'http://domain.uk': 'domain',
            'http://www.domain.com/path/': 'domain/path/',
            'http://www.domain.com/path/?query#fragment': 'domain/path/',
        }
        for k, v in expected.items():
            eq_(self.indexer.strip_url(k), v)


class TestExcludedFields(ESTestCase):
    def setUp(self):
        super(TestExcludedFields, self).setUp()
        self.website = website_factory()
        self.website.trending.create(region=2, value=50.0)
        self.website.popularity.create(region=2, value=142.0)
        self.reindex(Website)

    def test_excluded_fields(self):
        ok_(WebsiteIndexer.hidden_fields)

        data = WebsiteIndexer.search().execute().hits
        eq_(len(data), 1)
        obj = data[0]
        ok_('trending_2' not in obj)
        ok_('popularity_2' not in obj)

        ok_('description_translations' in obj)
        ok_('description' not in obj)
        ok_('description_l10n_english' not in obj)

        ok_('name_translations' in obj)
        ok_('name' not in obj)
        ok_('name_l10n_english' not in obj)
        ok_('name_sort' not in obj)
        ok_('name.raw' not in obj)

        ok_('short_name_translations' in obj)
        ok_('short_name' not in obj)
        ok_('short_name_l10n_english' not in obj)
