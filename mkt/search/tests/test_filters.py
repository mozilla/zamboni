# -*- coding: utf-8 -*-
import json

from nose.tools import eq_, ok_
from rest_framework.exceptions import ParseError

from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory
from django.test.utils import override_settings

import mkt
from mkt.constants.applications import DEVICE_CHOICES_IDS
from mkt.constants.features import FeatureProfile
from mkt.search.filters import (DeviceTypeFilter, ProfileFilter,
                                PublicAppsFilter, PublicSearchFormFilter,
                                RegionFilter, SearchQueryFilter, SortingFilter,
                                ValidAppsFilter)
from mkt.search.forms import TARAKO_CATEGORIES_MAPPING
from mkt.search.views import SearchView
from mkt.site.tests import TestCase
from mkt.webapps.indexers import WebappIndexer


class FilterTestsBase(TestCase):

    def setUp(self):
        super(FilterTestsBase, self).setUp()
        self.req = RequestFactory().get('/')
        self.req.user = AnonymousUser()
        self.view_class = SearchView

    def _filter(self, req=None, data=None):
        req = req or RequestFactory().get('/', data=data or {})
        req.user = AnonymousUser()
        queryset = WebappIndexer.search()
        for filter_class in self.filter_classes:
            queryset = filter_class().filter_queryset(req, queryset,
                                                      self.view_class)
        return queryset.to_dict()


class TestQueryFilter(FilterTestsBase):

    filter_classes = [SearchQueryFilter]

    def test_q(self):
        qs = self._filter(data={'q': 'search terms'})
        # Spot check a few queries.
        should = (qs['query']['function_score']['query']['bool']['should'])
        ok_({'match': {'name': {'query': 'search terms', 'boost': 4,
                                'slop': 1, 'type': 'phrase'}}}
            in should)
        ok_({'prefix': {'name': {'boost': 1.5, 'value': 'search terms'}}}
            in should)
        ok_({'match': {'name_l10n_english': {'query': 'search terms',
                                             'boost': 2.5}}}
            in should)
        ok_({'match': {'description_l10n_english':
            {'query': 'search terms',
             'boost': 0.6,
             'analyzer': 'english_analyzer',
             'type': 'phrase'}}} in should)

    def test_fuzzy_single_word(self):
        qs = self._filter(data={'q': 'term'})
        should = (qs['query']['function_score']['query']['bool']['should'])
        ok_({'fuzzy': {'tags': {'prefix_length': 1, 'value': 'term'}}}
            in should)

    def test_no_fuzzy_multi_word(self):
        qs = self._filter(data={'q': 'search terms'})
        qs_str = json.dumps(qs)
        ok_('fuzzy' not in qs_str)

    def test_preferred_regions(self):
        self.req = RequestFactory().get('/', data={'q': 'something'})
        self.req.REGION = mkt.regions.FRA
        qs = self._filter(req=self.req)
        should = (qs['query']['function_score']['query']['bool']['should'])
        ok_({'term': {'preferred_regions': {'value': mkt.regions.FRA.id,
                                            'boost': 4}}}
            in should)

    @override_settings(ES_USE_PLUGINS=True)
    def test_polish_analyzer(self):
        """
        Test that the polish analyzer is included correctly since it is an
        exception to the rest b/c it is a plugin.
        """
        with self.activate(locale='pl'):
            qs = self._filter(data={'q': u'próba'})
            should = (qs['query']['function_score']['query']['bool']['should'])
            ok_({'match': {'name_l10n_polish': {'query': u'pr\xf3ba',
                                                'boost': 2.5}}}
                in should)
            ok_({'match': {'description_l10n_polish': {'query': u'pr\xf3ba',
                                                       'boost': 0.6,
                                                       'analyzer': 'polish',
                                                       'type': 'phrase'}}}
                in should)


class TestFormFilter(FilterTestsBase):

    filter_classes = [PublicSearchFormFilter]

    def test_category(self):
        qs = self._filter(data={'cat': 'games'})
        ok_({'terms': {'category': ['games']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_tag(self):
        qs = self._filter(data={'tag': 'tarako'})
        ok_({'term': {'tags': 'tarako'}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_tarako_categories(self):
        qs = self._filter(data={'cat': 'tarako-lifestyle'})
        ok_({'terms':
             {'category': TARAKO_CATEGORIES_MAPPING['tarako-lifestyle']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(data={'cat': 'tarako-games'})
        ok_({'terms': {'category': TARAKO_CATEGORIES_MAPPING['tarako-games']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(data={'cat': 'tarako-tools'})
        ok_({'terms': {'category': TARAKO_CATEGORIES_MAPPING['tarako-tools']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_app_type(self):
        qs = self._filter(data={'app_type': ['hosted']})
        ok_({'terms': {'app_type': [1]}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_app_type_packaged(self):
        """Test packaged also includes privileged."""
        qs = self._filter(data={'app_type': ['packaged']})
        ok_({'terms': {'app_type': [2, 3]}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_manifest_url(self):
        url = 'http://hy.fr/manifest.webapp'
        qs = self._filter(data={'manifest_url': url})
        ok_({'term': {'manifest_url': url}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_offline(self):
        """Ensure we are filtering by offline-capable apps."""
        qs = self._filter(data={'offline': 'True'})
        ok_({'term': {'is_offline': True}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_online(self):
        """Ensure we are filtering by apps that require online access."""
        qs = self._filter(data={'offline': 'False'})
        ok_({'term': {'is_offline': False}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_offline_and_online(self):
        """Ensure we are not filtering by offline/online by default."""
        # Pass any form values other than 'offline' to create the dict.
        qs = self._filter(data={'cat': 'games'})
        ok_({'term': {'is_offline': True}}
            not in qs['query']['filtered']['filter']['bool']['must'])
        ok_({'term': {'is_offline': False}}
            not in qs['query']['filtered']['filter']['bool']['must'])

    def test_languages(self):
        qs = self._filter(data={'languages': 'fr'})
        ok_({'terms': {'supported_locales': ['fr']}}
            in qs['query']['filtered']['filter']['bool']['must'])

        qs = self._filter(data={'languages': 'ar,en-US'})
        ok_({'terms': {'supported_locales': ['ar', 'en-US']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_author(self):
        qs = self._filter(data={'author': 'Mozilla LABS'})
        ok_({'term': {'author.raw': u'mozilla labs'}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_installs_allowed_from(self):
        qs = self._filter(data={'installs_allowed_from': '*'})
        ok_({'term': {'installs_allowed_from': u'*'}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test that we don't filter by this field if not provided.
        qs = self._filter()
        ok_('installs_allowed_from' not in json.dumps(qs),
            "Unexpected 'installs_allowed_from' in query")

    def test_premium_types(self):
        def ptype(p):
            return mkt.ADDON_PREMIUM_API_LOOKUP.get(p)

        # Test a single premium type.
        qs = self._filter(data={'premium_types': ['free']})
        ok_({'terms': {'premium_type': [ptype('free')]}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test many premium types.
        qs = self._filter(data={'premium_types': ['free', 'free-inapp']})
        ok_({'terms': {'premium_type': [ptype('free'), ptype('free-inapp')]}}
            in qs['query']['filtered']['filter']['bool']['must'])
        # Test a non-existent premium type.
        with self.assertRaises(ParseError):
            self._filter(data={'premium_types': ['free', 'platinum']})

    def test_device(self):
        qs = self._filter(data={'dev': 'desktop'})
        ok_({'term': {'device': DEVICE_CHOICES_IDS['desktop']}}
            in qs['query']['filtered']['filter']['bool']['must'])

    def test_no_device_with_device_type(self):
        """Test that providing a device type w/o device doesn't filter."""
        qs = self._filter(data={'dev': '', 'device': 'firefoxos'})
        ok_('filtered' not in qs['query'].keys())


class TestPublicAppsFilter(FilterTestsBase):

    filter_classes = [PublicAppsFilter]

    def test_status(self):
        qs = self._filter(self.req)
        ok_({'term': {'status': mkt.STATUS_PUBLIC}}
            in qs['query']['filtered']['filter']['bool']['must'])
        ok_({'term': {'is_disabled': False}}
            in qs['query']['filtered']['filter']['bool']['must'])


class TestValidAppsFilter(FilterTestsBase):

    filter_classes = [ValidAppsFilter]

    def test_status(self):
        qs = self._filter(self.req)
        ok_({'terms': {'status': mkt.VALID_STATUSES}}
            in qs['query']['filtered']['filter']['bool']['must'])
        ok_({'term': {'is_disabled': False}}
            in qs['query']['filtered']['filter']['bool']['must'])


class TestDeviceTypeFilter(FilterTestsBase):

    filter_classes = [DeviceTypeFilter]

    def test_no_filters(self):
        qs = self._filter(self.req)
        ok_('filtered' not in qs['query'].keys())

    def test_mobile(self):
        self.req.MOBILE = True
        qs = self._filter(self.req)
        ok_({'term': {'uses_flash': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_gaia(self):
        self.req.GAIA = True
        qs = self._filter(self.req)
        ok_({'term': {'uses_flash': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_tablet(self):
        self.req.TABLET = True
        qs = self._filter(self.req)
        ok_('filtered' not in qs['query'].keys())

    def test_device_in_querystring(self):
        qs = self._filter(data={'dev': 'desktop'})
        ok_({'term': {'device': 1}}
            in qs['query']['filtered']['filter']['bool']['must'])
        qs = self._filter(data={'dev': 'android', 'device': 'mobile'})
        ok_({'term': {'device': 2}}
            in qs['query']['filtered']['filter']['bool']['must'])
        qs = self._filter(data={'dev': 'android', 'device': 'tablet'})
        ok_({'term': {'device': 3}}
            in qs['query']['filtered']['filter']['bool']['must'])
        qs = self._filter(data={'dev': 'firefoxos'})
        ok_({'term': {'device': 4}}
            in qs['query']['filtered']['filter']['bool']['must'])


class TestRegionFilter(FilterTestsBase):

    filter_classes = [RegionFilter]

    def test_no_region_default(self):
        qs = self._filter(self.req)
        ok_({'term': {'region_exclusions': mkt.regions.RESTOFWORLD.id}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_region(self):
        self.req.REGION = mkt.regions.BRA
        qs = self._filter(self.req)
        ok_({'term': {'region_exclusions': mkt.regions.BRA.id}}
            in qs['query']['filtered']['filter']['bool']['must_not'])


class TestProfileFilter(FilterTestsBase):

    filter_classes = [ProfileFilter]

    def profile_qs(self, disabled_features=None):
        if disabled_features is None:
            disabled_features = {}
        profile = FeatureProfile().fromkeys(FeatureProfile(), True)
        for feature in disabled_features:
            profile[feature] = False
        return {'pro': profile.to_signature(), 'dev': 'firefoxos'}

    def test_filter_all_features_present(self):
        qs = self._filter(data=self.profile_qs())
        ok_('filtered' not in qs['query'].keys())

    def test_filter_one_feature_present(self):
        qs = self._filter(data=self.profile_qs(disabled_features=['sms']))
        ok_({'term': {'features.has_sms': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])

    def test_filter_one_feature_present_desktop(self):
        data = self.profile_qs(disabled_features=['sms'])
        data['dev'] = 'desktop'
        qs = self._filter(data=data)
        ok_('filtered' not in qs['query'].keys())

    def test_filter_multiple_features_present(self):
        qs = self._filter(
            data=self.profile_qs(disabled_features=['sms', 'apps']))
        ok_({'term': {'features.has_sms': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])
        ok_({'term': {'features.has_apps': True}}
            in qs['query']['filtered']['filter']['bool']['must_not'])


class TestSortingFilter(FilterTestsBase):

    filter_classes = [SortingFilter]

    def test_sort(self):
        for api_sort, es_sort in SortingFilter.DEFAULT_SORTING.items():
            qs = self._filter(data={'sort': [api_sort]})
            if es_sort.startswith('-'):
                ok_({es_sort[1:]: {'order': 'desc'}} in qs['sort'], qs)
            else:
                eq_([es_sort], qs['sort'], qs)

    def test_sort_multiple(self):
        qs = self._filter(data={'sort': ['rating', 'created']})
        ok_({'bayesian_rating': {'order': 'desc'}} in qs['sort'])
        ok_({'created': {'order': 'desc'}} in qs['sort'])

    def test_sort_regional(self):
        """Popularity and trending use regional sorting for mature regions."""
        req = RequestFactory().get('/')
        req.REGION = mkt.regions.BRA
        # Default empty query searches use popularity.
        qs = self._filter(req)
        ok_({'popularity_%s'
             % mkt.regions.BRA.id: {'order': 'desc'}} in qs['sort'])
        # Popularity.
        req = RequestFactory().get('/', data={'sort': ['popularity']})
        req.REGION = mkt.regions.BRA
        qs = self._filter(req)
        ok_({'popularity_%s'
             % mkt.regions.BRA.id: {'order': 'desc'}} in qs['sort'])
        # Trending.
        req = RequestFactory().get('/', data={'sort': ['trending']})
        req.REGION = mkt.regions.BRA
        qs = self._filter(req)
        ok_({'trending_%s' % mkt.regions.BRA.id: {'order': 'desc'}}
            in qs['sort'])


class TestCombinedFilter(FilterTestsBase):
    """
    Basic test to ensure that when filters are combined they result in the
    expected query structure.

    """
    filter_classes = [SearchQueryFilter, PublicSearchFormFilter,
                      PublicAppsFilter, SortingFilter]

    def test_combined(self):
        qs = self._filter(data={'q': 'test', 'cat': 'games',
                                'sort': 'trending'})
        ok_(qs['query']['filtered']['query']['function_score'])
        ok_(qs['query']['filtered']['filter'])

        must = qs['query']['filtered']['filter']['bool']['must']
        ok_({'terms': {'category': ['games']}} in must)
        ok_({'term': {'status': 4}} in must)
        ok_({'term': {'is_disabled': False}} in must)

        ok_({'trending': {'order': 'desc'}} in qs['sort'])

        query = qs['query']['filtered']['query']
        ok_({'field_value_factor': {'field': 'boost'}}
            in query['function_score']['functions'])
        ok_({'match': {'name_l10n_english': {'boost': 2.5, 'query': u'test'}}}
            in query['function_score']['query']['bool']['should'])
