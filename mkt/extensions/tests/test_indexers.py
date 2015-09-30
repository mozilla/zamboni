# -*- coding: utf-8 -*-
from datetime import datetime

import mock
from nose.tools import eq_, ok_

from mkt.constants.base import STATUS_PENDING, STATUS_PUBLIC
from mkt.site.tests import ESTestCase, TestCase
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.search.utils import BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT, get_boost


class TestExtensionIndexer(TestCase):

    def setUp(self):
        self.indexer = Extension.get_indexer()()

    def _extension_factory(self, status=STATUS_PENDING, reviewed=None):
        if reviewed is None:
            # Microseconds are not saved by MySQL, so set it to 0 to make sure
            # our comparisons still work once the model is saved to the db.
            reviewed = datetime.utcnow().replace(microsecond=0)
        extension = Extension.objects.create(
            author=u'Test Aùthor', description=u'Test Desçription',
            name=u'Test Êxtension', last_updated=reviewed,
            slug=u'test-ëxtension')
        version = ExtensionVersion.objects.create(
            extension=extension, size=42, status=status, reviewed=reviewed,
            version='0.1')
        return extension, version

    def test_model(self):
        eq_(self.indexer.get_model(), Extension)
        ok_(isinstance(self.indexer, ExtensionIndexer))

    def test_get_mapping_ok(self):
        eq_(ExtensionIndexer.get_mapping_type_name(), 'extension')
        ok_(isinstance(self.indexer.get_mapping(), dict))

    def test_index(self):
        with self.settings(ES_INDEXES={'extension': 'extensions'}):
            eq_(ExtensionIndexer.get_index(), 'extensions')

    def test_mapping(self):
        mapping = ExtensionIndexer.get_mapping()
        eq_(mapping.keys(), ['extension'])
        eq_(mapping['extension']['_all'], {'enabled': False})

    def _get_doc(self, extension):
        return self.indexer.extract_document(extension.pk, extension)

    def test_extract_not_public(self):
        extension, version = self._extension_factory()
        doc = self._get_doc(extension)
        eq_(doc['id'], extension.id)
        eq_(doc['status'], extension.status)
        eq_(doc['latest_public_version'], None)

    def test_extract_disabled(self):
        extension, version = self._extension_factory(STATUS_PUBLIC)
        extension.update(disabled=True)
        doc = self._get_doc(extension)
        eq_(doc['id'], extension.id)
        eq_(doc['is_disabled'], True)
        eq_(doc['status'], STATUS_PUBLIC)
        eq_(doc['latest_public_version'],
            {'id': version.pk,
             'created': version.created.replace(microsecond=0),
             'size': 42, 'version': '0.1', })

    def test_extract_public(self):
        extension, version = self._extension_factory(STATUS_PUBLIC)
        doc = self._get_doc(extension)
        eq_(doc['id'], extension.id)
        eq_(doc['author'], extension.author)
        eq_(doc['created'], extension.created)
        eq_(doc['description'], [unicode(extension.description)])
        eq_(doc['description_translations'], [{
            'lang': u'en-US', 'string': unicode(extension.description)}])
        eq_(doc['default_language'], extension.default_language)
        eq_(doc['guid'], extension.uuid)
        eq_(doc['is_disabled'], extension.disabled)
        eq_(doc['last_updated'], extension.last_updated)
        eq_(doc['modified'], extension.modified)
        eq_(doc['name'], [unicode(extension.name)])
        eq_(doc['name_translations'], [{
            'lang': u'en-US', 'string': unicode(extension.name)}])
        eq_(doc['reviewed'], version.reviewed)
        eq_(doc['slug'], extension.slug)
        eq_(doc['status'], extension.status)
        eq_(doc['latest_public_version'],
            {'id': version.pk,
             'created': version.created.replace(microsecond=0),
             'size': 42, 'version': '0.1', })

    def test_reviewed_multiple_versions(self):
        extension, first_public_version = self._extension_factory(
            STATUS_PUBLIC, reviewed=self.days_ago(3))
        ExtensionVersion.objects.create(
            extension=extension, size=42, status=STATUS_PUBLIC,
            reviewed=self.days_ago(2), version='0.2')
        ExtensionVersion.objects.create(
            extension=extension, size=42, status=STATUS_PENDING,
            reviewed=self.days_ago(1), version='0.3')
        doc = self._get_doc(extension)
        eq_(doc['id'], extension.id)
        eq_(doc['reviewed'], first_public_version.reviewed)

    def test_extract_with_translations(self):
        extension, version = self._extension_factory()
        description = {
            'en-US': u'Description Extensiôn',
            'fr': u"Description de l'Ëxtension",
        }
        name = {
            'en-US': u'Namé Extension',
            'fr': u"Nom de l'Ëxtension",
        }
        extension.description = description
        extension.name = name
        extension.save()
        doc = self._get_doc(extension)

        eq_(sorted(doc['name']), [name['en-US'], name['fr']])
        eq_(sorted(doc['name_translations']),
            [{'lang': 'en-US', 'string': name['en-US']},
             {'lang': 'fr', 'string': name['fr']}])
        eq_(doc['name_l10n_french'], [name['fr']])
        eq_(doc['name_l10n_english'], [name['en-US']])
        eq_(doc['name_sort'], name['en-US'].lower())

        eq_(sorted(doc['description']),
            [description['en-US'], description['fr']])
        eq_(sorted(doc['description_translations']),
            [{'lang': 'en-US', 'string': description['en-US']},
             {'lang': 'fr', 'string': description['fr']}])
        eq_(doc['description_l10n_french'], [description['fr']])
        eq_(doc['description_l10n_english'], [description['en-US']])
        ok_('description_sort' not in doc)

    @mock.patch('mkt.search.indexers.MATURE_REGION_IDS', [42])
    def test_popularity(self):
        extension, version = self._extension_factory()
        # No installs.
        doc = self._get_doc(extension)
        # Boost is multiplied by BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT if it's
        # public.
        eq_(doc['boost'], 1.0 * BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT)
        eq_(doc['popularity'], 0)

        # Add some popularity.
        extension.popularity.create(region=0, value=50.0)
        # Test an adolescent region.
        extension.popularity.create(region=2, value=10.0)
        # Test a mature region.
        extension.popularity.create(region=42, value=10.0)

        doc = self._get_doc(extension)
        eq_(doc['boost'], get_boost(extension))
        eq_(doc['popularity'], 50)
        eq_(doc['popularity_42'], 10)
        # Adolescent regions popularity value is not stored.
        ok_('popularity_2' not in doc)

    @mock.patch('mkt.search.indexers.MATURE_REGION_IDS', [42])
    def test_trending(self):
        extension, version = self._extension_factory()
        extension.trending.create(region=0, value=10.0)
        # Test an adolescent region.
        extension.trending.create(region=2, value=50.0)
        # Test a mature region.
        extension.trending.create(region=42, value=50.0)

        doc = self._get_doc(extension)
        eq_(doc['trending'], 10.0)
        eq_(doc['trending_42'], 50.0)

        # Adolescent regions trending value is not stored.
        ok_('trending_2' not in doc)


class TestExtensionIndexerExcludedFields(ESTestCase):
    def setUp(self):
        super(TestExtensionIndexerExcludedFields, self).setUp()
        self.extension = Extension.objects.create()
        self.extension.trending.create(region=2, value=50.0)
        self.extension.popularity.create(region=2, value=142.0)
        self.refresh('extension')

    def test_excluded_fields(self):
        ok_(ExtensionIndexer.hidden_fields)

        data = ExtensionIndexer.search().execute().hits
        eq_(len(data), 1)
        obj = data[0]

        ok_('name_translations' in obj)
        ok_('name' not in obj)
        ok_('name_l10n_english' not in obj)
        ok_('name_sort' not in obj)
        ok_('name.raw' not in obj)

        ok_('trending_2' not in obj)
        ok_('popularity_2' not in obj)
        ok_('boost' not in obj)

        ok_('description_translations' in obj)
        ok_('description' not in obj)
        ok_('description_l10n_english' not in obj)


class TestExtensionIndexerBasicSearch(ESTestCase):
    def test_search_basic(self, status=STATUS_PENDING):
        extension = Extension.objects.create(
            name=u'Test Êxtension', slug=u'test-ëxtension')
        ExtensionVersion.objects.create(
            extension=extension, status=status, version='0.1')
        self.reindex(Extension)

        qs = ExtensionIndexer.search()
        results = qs.execute().hits
        eq_(len(results), 1)
        eq_(results.hits[0]['_id'], unicode(extension.pk))
