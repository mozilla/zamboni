# -*- coding: utf-8 -*-
import amo.tests
from amo.utils import to_language
from constants.applications import DEVICE_TYPES

from nose.tools import eq_, ok_

import mkt
from mkt.reviewers.models import EscalationQueue
from mkt.site.fixtures import fixture
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import AddonDeviceType, ContentRating, Webapp


class TestWebappIndexer(amo.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)

    def test_mapping_type_name(self):
        eq_(WebappIndexer.get_mapping_type_name(), 'webapp')

    def test_index(self):
        with self.settings(ES_INDEXES={'webapp': 'apps'}):
            eq_(WebappIndexer.get_index(), 'apps')

    def test_model(self):
        eq_(WebappIndexer.get_model(), Webapp)

    def test_mapping(self):
        mapping = WebappIndexer.get_mapping()
        eq_(mapping.keys(), ['webapp'])
        eq_(mapping['webapp']['_all'], {'enabled': False})
        eq_(mapping['webapp']['_boost'], {'name': '_boost', 'null_value': 1.0})

    def test_mapping_properties(self):
        # Spot check a few of the key properties.
        mapping = WebappIndexer.get_mapping()
        keys = mapping['webapp']['properties'].keys()
        for k in ('id', 'app_slug', 'category', 'default_locale',
                  'description', 'device', 'features', 'name', 'status'):
            ok_(k in keys, 'Key %s not found in mapping properties' % k)

    def _get_doc(self):
        qs = Webapp.objects.no_cache().filter(id__in=[self.app.pk])
        obj = qs[0]
        return obj, WebappIndexer.extract_document(obj.pk, obj)

    def test_extract(self):
        obj, doc = self._get_doc()
        eq_(doc['id'], obj.id)
        eq_(doc['app_slug'], obj.app_slug)
        eq_(doc['category'], [])
        eq_(doc['default_locale'], obj.default_locale)
        eq_(doc['description'], list(
            set(s for _, s in obj.translations[obj.description_id])))
        eq_(doc['description_translations'],
            [{'lang': to_language(l), 'string': s}
             for l, s in obj.translations[obj.description_id]])
        eq_(doc['device'], [])
        eq_(doc['name'], list(
            set(s for _, s in obj.translations[obj.name_id])))
        eq_(doc['name_translations'],
            [{'lang': to_language(l), 'string': s}
             for l, s in obj.translations[obj.name_id]])
        eq_(doc['status'], obj.status)
        eq_(doc['is_escalated'], False)
        eq_(doc['latest_version']['status'], amo.STATUS_PUBLIC)
        eq_(doc['latest_version']['has_editor_comment'], False)
        eq_(doc['latest_version']['has_info_request'], False)

    def test_extract_category(self):
        self.app.update(categories=['books'])
        obj, doc = self._get_doc()
        eq_(doc['category'], ['books'])

    def test_extract_device(self):
        device = DEVICE_TYPES.keys()[0]
        AddonDeviceType.objects.create(addon=self.app, device_type=device)

        obj, doc = self._get_doc()
        eq_(doc['device'], [device])

    def test_extract_features(self):
        enabled = ('has_apps', 'has_sms', 'has_geolocation')
        self.app.current_version.features.update(
            **dict((k, True) for k in enabled))
        obj, doc = self._get_doc()
        for k, v in doc['features'].iteritems():
            eq_(v, k in enabled)

    def test_extract_regions(self):
        self.app.addonexcludedregion.create(region=mkt.regions.BR.id)
        self.app.addonexcludedregion.create(region=mkt.regions.UK.id)
        obj, doc = self._get_doc()
        self.assertSetEqual(doc['region_exclusions'],
                            set([mkt.regions.BR.id, mkt.regions.UK.id]))

    def test_extract_supported_locales(self):
        locales = 'en-US,es,pt-BR'
        self.app.current_version.update(supported_locales=locales)
        obj, doc = self._get_doc()
        self.assertSetEqual(doc['supported_locales'], set(locales.split(',')))

    def test_extract_latest_version(self):
        amo.tests.version_factory(addon=self.app, version='43.0',
                                  has_editor_comment=True,
                                  has_info_request=True,
                                  file_kw=dict(status=amo.STATUS_REJECTED))
        obj, doc = self._get_doc()
        eq_(doc['latest_version']['status'], amo.STATUS_REJECTED)
        eq_(doc['latest_version']['has_editor_comment'], True)
        eq_(doc['latest_version']['has_info_request'], True)

    def test_extract_is_escalated(self):
        EscalationQueue.objects.create(addon=self.app)
        obj, doc = self._get_doc()
        eq_(doc['is_escalated'], True)

    def test_extract_content_ratings(self):
        ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.CLASSIND.id,
            rating=0)
        ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.GENERIC.id,
            rating=0)
        ContentRating.objects.create(
            addon=self.app, ratings_body=mkt.ratingsbodies.PEGI.id,
            rating=mkt.ratingsbodies.PEGI_12.id)

        obj, doc = self._get_doc()
        content_ratings = doc['content_ratings']

        eq_(len(content_ratings), 3)
        eq_(doc['content_ratings']['classind'],
            {'body': mkt.ratingsbodies.CLASSIND.id,
             'rating': mkt.ratingsbodies.CLASSIND_L.id})
        eq_(doc['content_ratings']['generic'],
            {'body': mkt.ratingsbodies.GENERIC.id,
             'rating': mkt.ratingsbodies.GENERIC_3.id})
        eq_(doc['content_ratings']['pegi'],
            {'body': mkt.ratingsbodies.PEGI.id,
             'rating': mkt.ratingsbodies.PEGI_12.id})

    def test_extract_release_notes(self):
        release_notes = {
            'fr': u'Dès notes de version.',
            'en-US': u'Some release nötes.'
        }
        version = self.app.current_version
        version.releasenotes = release_notes
        version.save()
        obj, doc = self._get_doc()
        eq_(doc['release_notes_translations'][0],
            {'lang': 'en-US', 'string': release_notes['en-US']})
        eq_(doc['release_notes_translations'][1],
            {'lang': 'fr', 'string': release_notes['fr']})
