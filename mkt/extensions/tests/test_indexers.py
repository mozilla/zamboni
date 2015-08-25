# -*- coding: utf-8 -*-
from nose.tools import eq_, ok_

from mkt.constants.base import STATUS_PENDING
from mkt.site.tests import ESTestCase, TestCase
from mkt.extensions.indexers import ExtensionIndexer
from mkt.extensions.models import Extension


class TestWebsiteIndexer(TestCase):

    def setUp(self):
        self.indexer = Extension.get_indexer()()

    def _extension_factory(self):
        return Extension.objects.create(**{
            'name': u'Test Êxtension',
            'slug': u'test-ëxtension',
            'status': STATUS_PENDING,
            'version': '0.42',
        })

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

    def _get_doc(self):
        return self.indexer.extract_document(self.obj.pk, self.obj)

    def test_extract(self):
        self.obj = self._extension_factory()
        doc = self._get_doc()
        eq_(doc['id'], self.obj.id)
        eq_(doc['created'], self.obj.created)
        eq_(doc['default_language'], self.obj.default_language)
        eq_(doc['modified'], self.obj.modified)
        eq_(doc['name'], [unicode(self.obj.name)])
        eq_(doc['name_translations'], [{
            'lang': u'en-US', 'string': unicode(self.obj.name)}])
        eq_(doc['slug'], self.obj.slug)
        eq_(doc['status'], self.obj.status)
        eq_(doc['version'], self.obj.version)

    def test_extract_with_translations(self):
        self.obj = self._extension_factory()
        name = {
            'en-US': u'Namé Extension',
            'fr': u"Nom de l'Ëxtension",
        }
        self.obj.name = name
        self.obj.save()
        doc = self._get_doc()

        eq_(sorted(doc['name']), [name['en-US'], name['fr']])
        eq_(sorted(doc['name_translations']),
            [{'lang': 'en-US', 'string': name['en-US']},
             {'lang': 'fr', 'string': name['fr']}])
        eq_(doc['name_l10n_french'], [name['fr']])
        eq_(doc['name_l10n_english'], [name['en-US']])
        eq_(doc['name_sort'], name['en-US'].lower())


class TestExcludedFields(ESTestCase):
    def setUp(self):
        super(TestExcludedFields, self).setUp()
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
