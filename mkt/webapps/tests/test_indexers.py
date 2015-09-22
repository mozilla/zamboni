# -*- coding: utf-8 -*-
from django.test.utils import override_settings

import json
from nose.tools import eq_, ok_

import mkt
from mkt.constants.applications import DEVICE_TYPES
from mkt.reviewers.models import EscalationQueue, RereviewQueue
from mkt.search.utils import BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT, get_boost
from mkt.site.fixtures import fixture
from mkt.site.tests import ESTestCase, TestCase
from mkt.site.utils import version_factory
from mkt.translations.utils import to_language
from mkt.users.models import UserProfile
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import AddonDeviceType, ContentRating, Webapp


class TestWebappIndexer(TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=31337)

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
        eq_(mapping['webapp']['properties']['boost'],
            {'type': 'float', 'doc_values': True})

    def test_mapping_properties(self):
        # Spot check a few of the key properties.
        mapping = WebappIndexer.get_mapping()
        keys = mapping['webapp']['properties'].keys()
        for k in ('id', 'app_slug', 'category', 'default_locale',
                  'description', 'device', 'features', 'name', 'status'):
            ok_(k in keys, 'Key %s not found in mapping properties' % k)

    def _get_doc(self):
        qs = Webapp.objects.filter(id__in=[self.app.pk])
        obj = qs[0]
        return obj, WebappIndexer.extract_document(obj.pk, obj)

    def test_extract(self):
        obj, doc = self._get_doc()
        eq_(doc['id'], obj.id)
        eq_(doc['guid'], obj.guid)
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
        eq_(doc['promo_img_hash'], obj.promo_img_hash)
        eq_(doc['status'], obj.status)
        eq_(doc['trending'], 0)
        eq_(doc['is_escalated'], False)
        eq_(doc['latest_version']['status'], mkt.STATUS_PUBLIC)
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
        self.app.addonexcludedregion.create(region=mkt.regions.BRA.id)
        self.app.addonexcludedregion.create(region=mkt.regions.GBR.id)
        obj, doc = self._get_doc()
        self.assertSetEqual(doc['region_exclusions'],
                            set([mkt.regions.BRA.id, mkt.regions.GBR.id]))

    def test_extract_supported_locales(self):
        self.app.update(default_locale='de')
        locales = 'en-US,es,pt-BR'
        self.app.current_version.update(supported_locales=locales)
        obj, doc = self._get_doc()
        self.assertSetEqual(doc['supported_locales'],
                            set(['de'] + locales.split(',')))

    def test_extract_latest_version(self):
        created_date = self.days_ago(5).replace(microsecond=0)
        nomination_date = self.days_ago(3).replace(microsecond=0)

        version_factory(
            addon=self.app, version='43.0',
            has_editor_comment=True,
            has_info_request=True,
            created=created_date,
            nomination=nomination_date,
            file_kw=dict(status=mkt.STATUS_REJECTED))
        obj, doc = self._get_doc()
        eq_(doc['latest_version']['status'], mkt.STATUS_REJECTED)
        eq_(doc['latest_version']['has_editor_comment'], True)
        eq_(doc['latest_version']['has_info_request'], True)
        eq_(doc['latest_version']['created_date'], created_date)
        eq_(doc['latest_version']['nomination_date'], nomination_date)

    def test_extract_is_escalated(self):
        EscalationQueue.objects.create(addon=self.app)
        obj, doc = self._get_doc()
        eq_(doc['is_escalated'], True)
        self.assertCloseToNow(doc['escalation_date'])

    def test_extract_is_rereviewed(self):
        RereviewQueue.objects.create(addon=self.app)
        obj, doc = self._get_doc()
        eq_(doc['is_rereviewed'], True)
        self.assertCloseToNow(doc['rereview_date'])

    def test_extract_is_priority(self):
        self.app.update(priority_review=True)
        obj, doc = self._get_doc()
        eq_(doc['is_priority'], True)

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

    def test_extract_installs_allowed_from(self):
        # Test 'installs_allowed_from' empty defaults to ['*'].
        self.app.current_version.manifest_json.update(manifest=json.dumps({}))
        obj, doc = self._get_doc()
        eq_(doc['installs_allowed_from'], ['*'])

        # Test single value.
        self.app.current_version.manifest_json.update(manifest=json.dumps({
            'installs_allowed_from': ['http://a.com']}))
        obj, doc = self._get_doc()
        eq_(doc['installs_allowed_from'], ['http://a.com'])

        # Test multiple value.
        self.app.current_version.manifest_json.update(manifest=json.dumps({
            'installs_allowed_from': ['http://a.com', 'http://b.com']}))
        obj, doc = self._get_doc()
        eq_(doc['installs_allowed_from'], ['http://a.com', 'http://b.com'])

    def test_installs_to_popularity(self):
        # No installs.
        obj, doc = self._get_doc()
        # Boost is multiplied by BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT if it's
        # public.
        eq_(doc['boost'], 1 * BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT)
        eq_(doc['popularity'], 0)

        # Many installs.
        self.app.popularity.create(region=0, value=50.0)
        # Test an adolescent region.
        self.app.popularity.create(region=2, value=10.0)
        # Test a mature region.
        self.app.popularity.create(region=7, value=10.0)

        obj, doc = self._get_doc()
        eq_(doc['boost'], get_boost(self.app))
        eq_(doc['popularity'], 50)
        eq_(doc['popularity_7'], 10)
        # Adolescent regions popularity value is not stored.
        ok_('popularity_2' not in doc)

    @override_settings(QA_APP_ID=337141)
    def test_popularity_qa_app(self):
        self.app.popularity.create(region=0, value=50.0)
        obj, doc = self._get_doc()
        eq_(doc['boost'], 1 * BOOST_MULTIPLIER_FOR_PUBLIC_CONTENT)
        eq_(doc['popularity'], 0)
        eq_(doc['popularity_7'], 0)
        eq_(doc['trending'], 0)
        eq_(doc['trending_7'], 0)

    def test_trending(self):
        self.app.trending.create(region=0, value=10.0)
        # Test an adolescent region.
        self.app.trending.create(region=2, value=50.0)
        # Test a mature region.
        self.app.trending.create(region=7, value=50.0)

        obj, doc = self._get_doc()
        eq_(doc['trending'], 10.0)
        eq_(doc['trending_7'], 50.0)
        # Adolescent regions trending value is not stored.
        ok_('trending_2' not in doc)


class TestExcludedFields(ESTestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        super(TestExcludedFields, self).setUp()
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.trending.create(region=2, value=50.0)
        self.webapp.popularity.create(region=2, value=142.0)
        self.reindex(Webapp)

    def test_excluded_fields(self):
        ok_(WebappIndexer.hidden_fields)

        data = WebappIndexer.search().execute().hits
        eq_(len(data), 1)
        obj = data[0]
        ok_('trending_2' not in obj)
        ok_('popularity_2' not in obj)
        ok_('name_translations' in obj)
        ok_('name' not in obj)
        ok_('name_l10n_english' not in obj)
        ok_('name_sort' not in obj)
        ok_('name.raw' not in obj)


class TestAppFilter(ESTestCase):

    def setUp(self):
        super(TestAppFilter, self).setUp()
        self.apps = [mkt.site.tests.app_factory() for i in range(11)]
        self.app_ids = [a.id for a in self.apps]
        self.request = mkt.site.tests.req_factory_factory()
        self.refresh('webapp')

    def test_app_ids(self):
        """
        Test all apps are returned if app IDs is passed. Natural ES limit is
        10.
        """
        sq = WebappIndexer.filter_by_apps(app_ids=self.app_ids)
        results = sq.execute().hits
        eq_(len(results), 11)
