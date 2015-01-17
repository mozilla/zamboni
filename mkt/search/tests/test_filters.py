import json

from nose.tools import eq_, ok_

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

import mkt
from mkt import regions
from mkt.api.tests.test_oauth import BaseOAuth
from mkt.constants.applications import DEVICE_CHOICES_IDS
from mkt.constants.features import FeatureProfile
from mkt.regions import set_region
from mkt.reviewers.forms import ApiReviewersSearchForm
from mkt.search.forms import ApiSearchForm, TARAKO_CATEGORIES_MAPPING
from mkt.search.views import (_sort_search, DEFAULT_SORTING,
                              search_form_to_es_fields)
from mkt.site.fixtures import fixture
from mkt.webapps.indexers import WebappIndexer


class TestSearchFilters(BaseOAuth):
    fixtures = fixture('webapp_337141', 'user_2519')

    def setUp(self):
        super(TestSearchFilters, self).setUp()
        self.req = RequestFactory().get('/')
        self.req.user = AnonymousUser()

        # Pick a region that has relatively few filters.
        set_region(regions.GBR.slug)

        self.form_class = ApiSearchForm

    def _grant(self, rules):
        self.grant_permission(self.profile, rules)
        self.req.groups = self.profile.groups.all()

    def _filter(self, req, data, **kwargs):
        # Note: both the request and the data sent to the form are important,
        # because the form does not handle everything. In particular, it does
        # not handle regions and features, since those are not-specific to the
        # search form and apply to multiple API endpoints.
        form = self.form_class(data)
        if form.is_valid():
            form_data = form.cleaned_data
            sq = WebappIndexer.get_app_filter(
                self.req, search_form_to_es_fields(form_data))
            return _sort_search(self.req, sq, form_data).to_dict()
        else:
            return form.errors.copy()

    def _request_from_features(self, disabled_features=None, dev='firefoxos',
                               region=None):
        if disabled_features is None:
            disabled_features = {}
        profile = FeatureProfile().fromkeys(FeatureProfile(), True)
        for feature in disabled_features:
            profile[feature] = False
        data = {'pro': profile.to_signature(), 'dev': dev}
        request = RequestFactory().get('/', data=data)
        request.REGION = region
        return request

    def test_q(self):
        qs = self._filter(self.req, {'q': 'search terms'})
        ok_(qs['query']['filtered']['query'])
        # Spot check a few queries.
        should = (qs['query']['filtered']['query']['function_score']['query']
                  ['bool']['should'])
        ok_({'match': {'name': {'query': 'search terms', 'boost': 4,
                                'slop': 1, 'type': 'phrase'}}}
            in should)
        ok_({'prefix': {'name': {'boost': 1.5, 'value': 'search terms'}}}
            in should)
        ok_({'match': {'name_english': {'query': 'search terms',
                                        'boost': 2.5}}}
            in should)

    def test_fuzzy_single_word(self):
        qs = self._filter(self.req, {'q': 'term'})
        should = (qs['query']['filtered']['query']['function_score']['query']
                  ['bool']['should'])
        ok_({'fuzzy': {'tags': {'prefix_length': 1, 'value': 'term'}}}
            in should)

    def test_no_fuzzy_multi_word(self):
        qs = self._filter(self.req, {'q': 'search terms'})
        qs_str = json.dumps(qs)
        ok_('fuzzy' not in qs_str)

    def _status_check(self, query, expected=mkt.STATUS_PUBLIC):
        qs = self._filter(self.req, query)
        ok_({'term': {'status': expected}}
            in qs['query']['filtered']['filter']['bool']['must'],
            'Unexpected status. Expected: %s.' % expected)

    def test_status(self):
        self.form_class = ApiReviewersSearchForm
        # Test all that should end up being public.
        # Note: Status permission can't be checked here b/c the acl check
        # happens in the view, not the _filter_search call.
        self._status_check({})
        self._status_check({'status': 'public'})
        self._status_check({'status': 'rejected'})
        # Test a bad value.
        qs = self._filter(self.req, {'status': 'vindaloo'})
        ok_(u'Select a valid choice' in qs['status'][0])

    def test_category(self):
        qs = self._filter(self.req, {'cat': 'games'})
        ok_({'terms': {'category': ['games']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_tag(self):
        qs = self._filter(self.req, {'tag': 'tarako'})
        ok_({'term': {'tags': 'tarako'}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_tarako_categories(self):
        qs = self._filter(self.req, {'cat': 'tarako-lifestyle'})
        ok_({'terms':
             {'category': TARAKO_CATEGORIES_MAPPING['tarako-lifestyle']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(self.req, {'cat': 'tarako-games'})
        ok_({'terms': {'category': TARAKO_CATEGORIES_MAPPING['tarako-games']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(self.req, {'cat': 'tarako-tools'})
        ok_({'terms': {'category': TARAKO_CATEGORIES_MAPPING['tarako-tools']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_device(self):
        qs = self._filter(self.req, {'dev': 'desktop'})
        ok_({'term': {'device': DEVICE_CHOICES_IDS['desktop']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_premium_types(self):
        ptype = lambda p: mkt.ADDON_PREMIUM_API_LOOKUP.get(p)
        # Test a single premium type.
        qs = self._filter(self.req, {'premium_types': ['free']})
        ok_({'terms': {'premium_type': [ptype('free')]}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test many premium types.
        qs = self._filter(self.req, {'premium_types': ['free', 'free-inapp']})
        ok_({'terms': {'premium_type': [ptype('free'), ptype('free-inapp')]}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test a non-existent premium type.
        qs = self._filter(self.req, {'premium_types': ['free', 'platinum']})
        ok_(u'Select a valid choice' in qs['premium_types'][0])

    def test_app_type(self):
        qs = self._filter(self.req, {'app_type': ['hosted']})
        ok_({'terms': {'app_type': [1]}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_app_type_packaged(self):
        """Test packaged also includes privileged."""
        qs = self._filter(self.req, {'app_type': ['packaged']})
        ok_({'terms': {'app_type': [2, 3]}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_manifest_url(self):
        url = 'http://hy.fr/manifest.webapp'
        qs = self._filter(self.req, {'manifest_url': url})
        ok_({'term': {'manifest_url': url}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_offline(self):
        """Ensure we are filtering by offline-capable apps."""
        qs = self._filter(self.req, {'offline': 'True'})
        ok_({'term': {'is_offline': True}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_online(self):
        """Ensure we are filtering by apps that require online access."""
        qs = self._filter(self.req, {'offline': 'False'})
        ok_({'term': {'is_offline': False}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_offline_and_online(self):
        """Ensure we are not filtering by offline/online by default."""
        qs = self._filter(self.req, {})
        ok_({'term': {'is_offline': True}}
            not in qs['query']['filtered']['filter']['bool']['must'])
        ok_({'term': {'is_offline': False}}
            not in qs['query']['filtered']['filter']['bool']['must'])

    def test_languages(self):
        qs = self._filter(self.req, {'languages': 'fr'})
        ok_({'terms': {'supported_locales': ['fr']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(self.req, {'languages': 'ar,en-US'})
        ok_({'terms': {'supported_locales': ['ar', 'en-US']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_author(self):
        qs = self._filter(self.req, {'author': 'Mozilla LABS'})
        ok_({'term': {'author.raw': u'mozilla labs'}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_installs_allowed_from(self):
        qs = self._filter(self.req, {'installs_allowed_from': '*'})
        ok_({'term': {'installs_allowed_from': u'*'}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test that we don't filter by this field if not provided.
        qs = self._filter(self.req, {})
        ok_('installs_allowed_from' not in json.dumps(qs),
            "Unexpected 'installs_allowed_from' in query")

    def test_region_exclusions(self):
        self.req.REGION = regions.COL
        qs = self._filter(self.req, {'q': 'search terms'})
        ok_({'term': {'region_exclusions': regions.COL.id}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_sort(self):
        for api_sort, es_sort in DEFAULT_SORTING.items():
            qs = self._filter(self.req, {'sort': [api_sort]})
            if es_sort.startswith('-'):
                ok_({es_sort[1:]: {'order': 'desc'}} in qs['sort'], qs)
            else:
                eq_([es_sort], qs['sort'], qs)

    def test_sort_multiple(self):
        qs = self._filter(self.req, {'sort': ['rating', 'created']})
        ok_({'bayesian_rating': {'order': 'desc'}} in qs['sort'])
        ok_({'created': {'order': 'desc'}} in qs['sort'])

    def test_sort_regional(self):
        """Popularity and trending use regional sorting for mature regions."""
        self.req.REGION = regions.BRA
        # Popularity.
        qs = self._filter(self.req, {'sort': ['popularity']})
        ok_({'popularity_%s'
             % regions.BRA.id: {'order': 'desc'}} in qs['sort'])
        # Trending.
        qs = self._filter(self.req, {'sort': ['trending']})
        ok_({'trending_%s' % regions.BRA.id: {'order': 'desc'}} in qs['sort'])

    def test_filter_all_features_present(self):
        self.req = self._request_from_features()
        qs = self._filter(self.req, {'q': 'search terms'})
        ok_(not 'must_not' in qs['query']['filtered']['filter']['bool'])

    def test_filter_all_features_present_and_region(self):
        self.req = self._request_from_features(region=regions.GBR)
        qs = self._filter(self.req, {'q': 'search terms'})
        must_not = qs['query']['filtered']['filter']['bool']['must_not']
        for conditions in must_not:
            for term in conditions['term']:
                ok_(not term.startswith('features'))

    def test_filter_one_features_present(self):
        self.req = self._request_from_features(disabled_features=['sms'])
        qs = self._filter(self.req, {'q': 'search terms', 'region': 'None'})
        ok_({'term': {'features.has_sms': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_filter_multiple_features_present(self):
        self.req = self._request_from_features(
            disabled_features=['sms', 'apps'])
        qs = self._filter(self.req, {'q': 'search terms', 'region': 'None'})
        ok_({'term': {'features.has_sms': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])
        ok_({'term': {'features.has_apps': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])
