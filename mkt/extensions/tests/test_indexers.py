# -*- coding: utf-8 -*-
from nose.tools import eq_, ok_

from mkt.constants.base import STATUS_PENDING, STATUS_PUBLIC
from mkt.site.tests import ESTestCase, TestCase
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension, ExtensionVersion


class TestExtensionIndexer(TestCase):

    def setUp(self):
        self.indexer = Extension.get_indexer()()

    def _extension_factory(self, status=STATUS_PENDING):
        extension = Extension.objects.create(
            name=u'Test Êxtension', slug=u'test-ëxtension')
        version = ExtensionVersion.objects.create(
            extension=extension, size=42, status=status, version='0.1')
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

    def test_extract_public(self):
        extension, version = self._extension_factory(STATUS_PUBLIC)
        doc = self._get_doc(extension)
        eq_(doc['id'], extension.id)
        eq_(doc['created'], extension.created)
        eq_(doc['default_language'], extension.default_language)
        eq_(doc['modified'], extension.modified)
        eq_(doc['name'], [unicode(extension.name)])
        eq_(doc['name_translations'], [{
            'lang': u'en-US', 'string': unicode(extension.name)}])
        eq_(doc['slug'], extension.slug)
        eq_(doc['status'], extension.status)
        eq_(doc['latest_public_version'],
            {'id': version.pk, 'size': 42, 'version': '0.1', })

    def test_extract_with_translations(self):
        extension, version = self._extension_factory()
        name = {
            'en-US': u'Namé Extension',
            'fr': u"Nom de l'Ëxtension",
        }
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


class TestExtensionIndexerExcludedFields(ESTestCase):
    def setUp(self):
        super(TestExtensionIndexerExcludedFields, self).setUp()
        self.extension = Extension.objects.create()
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
