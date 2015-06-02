from django.conf import settings
from django.utils import translation

from elasticsearch_dsl import F, query
from elasticsearch_dsl.filter import Bool
from rest_framework.filters import BaseFilterBackend

import mkt
from mkt.api.base import form_errors, get_region_from_request
from mkt.constants.applications import get_device_id
from mkt.features.utils import get_feature_profile


class SearchQueryFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that scores the given ES queryset
    with a should query based on the search query found in the current
    request's query parameters.
    """
    def _get_locale_analyzer(self, lang):
        analyzer = mkt.SEARCH_LANGUAGE_TO_ANALYZER.get(lang)
        if (analyzer in mkt.SEARCH_ANALYZER_PLUGINS and
                not settings.ES_USE_PLUGINS):
            analyzer = None
        return analyzer

    def filter_queryset(self, request, queryset, view):

        q = request.GET.get('q', '').lower()
        lang = translation.get_language()
        analyzer = self._get_locale_analyzer(lang)

        if not q:
            return queryset

        should = []
        rules = [
            (query.Match, {'query': q, 'boost': 3, 'analyzer': 'standard'}),
            (query.Match, {'query': q, 'boost': 4, 'type': 'phrase',
                           'slop': 1}),
            (query.Prefix, {'value': q, 'boost': 1.5}),
        ]

        # Only add fuzzy queries if q is a single word. It doesn't make sense
        # to do a fuzzy query for multi-word queries.
        if ' ' not in q:
            rules.append(
                (query.Fuzzy, {'value': q, 'boost': 2, 'prefix_length': 1}))

        # Apply rules to search on few base fields. Some might not be present
        # in every document type / indexes.
        for k, v in rules:
            for field in ('name', 'short_name', 'title', 'app_slug', 'author',
                          'url'):
                should.append(k(**{field: v}))

        # Exact matches need to be queried against a non-analyzed field. Let's
        # do a term query on `name.raw` for an exact match against the item
        # name and give it a good boost since this is likely what the user
        # wants.
        should.append(query.Term(**{'name.raw': {'value': q, 'boost': 10}}))

        if analyzer:
            should.append(
                query.Match(**{'name_l10n_%s' % analyzer: {'query': q,
                                                           'boost': 2.5}}))
            should.append(
                query.Match(**{'short_name_l10n_%s' % analyzer: {
                    'query': q,
                    'boost': 2.5}}))

        # Add searches on the description field.
        should.append(
            query.Match(description={'query': q, 'boost': 0.8,
                                     'type': 'phrase'}))

        if analyzer:
            desc_field = 'description_l10n_%s' % analyzer
            desc_analyzer = ('%s_analyzer' % analyzer
                             if analyzer in mkt.STEMMER_MAP else analyzer)
            should.append(
                query.Match(
                    **{desc_field: {'query': q, 'boost': 0.6, 'type': 'phrase',
                                    'analyzer': desc_analyzer}}))

        # Add searches on tag field.
        should.append(query.Match(tags={'query': q}))
        if ' ' not in q:
            should.append(query.Fuzzy(tags={'value': q, 'prefix_length': 1}))

        # Add a boost for the preferred region, if it exists.
        region = get_region_from_request(request)
        if region:
            should.append(query.Term(**{'preferred_regions': {
                'value': region.id,
                'boost': 4}}))

        return queryset.query(
            'function_score',
            query=query.Bool(should=should),
            functions=[query.SF('field_value_factor', field='boost')])


class SearchFormFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters the given queryset
    based on `self.form_class`.

    """
    # A mapping of form fields to Elasticsearch fields for those that differ.
    FORM_TO_FIELD_MAP = {
        'author': 'author.raw',
        'cat': 'category',
        'has_info_request': 'latest_version.has_info_request',
        'has_editor_comment': 'latest_version.has_editor_comment',
        'languages': 'supported_locales',
        'offline': 'is_offline',
        'premium_types': 'premium_type',
        'tag': 'tags'
    }

    def filter_queryset(self, request, queryset, view):
        form = view.form_class(request.GET)
        if not form.is_valid():
            raise form_errors(form)

        self.form_data = form.cleaned_data

        data = {}
        for k, v in self.form_data.items():
            data[self.FORM_TO_FIELD_MAP.get(k, k)] = v

        # Must filters.
        must = []
        for field in self.VALID_FILTERS:
            value = data.get(field)
            if value is not None:
                if type(value) == list:
                    filter_type = 'terms'
                else:
                    filter_type = 'term'
                must.append(F(filter_type, **{field: value}))

        if must:
            return queryset.filter(Bool(must=must))

        return queryset


class PublicSearchFormFilter(SearchFormFilter):
    VALID_FILTERS = ['app_type', 'author.raw', 'category', 'device',
                     'installs_allowed_from', 'is_offline', 'manifest_url',
                     'premium_type', 'supported_locales', 'tags']


class ReviewerSearchFormFilter(SearchFormFilter):
    VALID_FILTERS = ['app_type', 'author.raw', 'category', 'device',
                     'latest_version.has_editor_comment',
                     'latest_version.has_info_request',
                     'latest_version.status',
                     'installs_allowed_from', 'is_escalated', 'is_offline',
                     'manifest_url', 'premium_type', 'status',
                     'supported_locales', 'tags']

    def filter_queryset(self, request, queryset, view):
        queryset = super(ReviewerSearchFormFilter,
                         self).filter_queryset(request, queryset, view)

        # Special case for `is_tarako`, which gets converted to a tag filter.
        is_tarako = self.form_data.get('is_tarako')
        if is_tarako is not None:
            if is_tarako:
                queryset = queryset.filter(
                    Bool(must=[F('term', tags='tarako')]))
            else:
                queryset = queryset.filter(
                    Bool(must=[~F('term', tags='tarako')]))

        return queryset


class WebsiteSearchFormFilter(SearchFormFilter):
    VALID_FILTERS = ['keywords', 'category', 'device']


class ReviewerWebsiteSearchFormFilter(SearchFormFilter):
    VALID_FILTERS = ['keywords', 'category', 'device', 'status', 'is_disabled']


class PublicAppsFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters only public items --
    those with PUBLIC status and not disabled.

    """
    def filter_queryset(self, request, queryset, view):
        return queryset.filter(
            Bool(must=[F('term', status=mkt.STATUS_PUBLIC),
                       F('term', is_disabled=False)]))


class ValidAppsFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters only valid items --
    those with any valid status and not disabled or deleted.

    """
    def filter_queryset(self, request, queryset, view):
        return queryset.filter(
            Bool(must=[F('terms', status=mkt.VALID_STATUSES),
                       F('term', is_disabled=False)]))


class DeviceTypeFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters based on the matching
    device type provided.

    """
    def filter_queryset(self, request, queryset, view):

        device_id = get_device_id(request)
        data = {
            'gaia': getattr(request, 'GAIA', False),
            'mobile': getattr(request, 'MOBILE', False),
            'tablet': getattr(request, 'TABLET', False),
        }
        flash_incompatible = data['mobile'] or data['gaia']

        if device_id:
            queryset = queryset.filter(
                Bool(must=[F('term', device=device_id)]))
        if flash_incompatible:
            queryset = queryset.filter(
                Bool(must_not=[F('term', uses_flash=True)]))

        return queryset


class RegionFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters based on the matching
    region provided.

    """
    def filter_queryset(self, request, queryset, view):

        region = get_region_from_request(request)
        if region:
            return queryset.filter(
                Bool(must_not=[F('term', region_exclusions=region.id)]))

        return queryset


class ProfileFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that filters based on the feature
    profile provided.

    """
    def filter_queryset(self, request, queryset, view):
        profile = get_feature_profile(request)
        if profile:
            must_not = []
            for k in profile.to_kwargs(prefix='features.has_').keys():
                must_not.append(F('term', **{k: True}))
            if must_not:
                return queryset.filter(Bool(must_not=must_not))

        return queryset


class SortingFilter(BaseFilterBackend):
    """
    A django-rest-framework filter backend that applies sorting based on the
    form data provided.

    """
    DEFAULT_SORTING = {
        'popularity': '-popularity',
        'rating': '-bayesian_rating',
        'created': '-created',
        'reviewed': '-reviewed',
        'name': 'name_sort',
        'trending': '-trending',
    }

    def _get_regional_sort(self, region, field):
        """
        A helper method to return the sort field with region for mature
        regions, otherwise returns the field.

        """
        if region and not region.adolescent:
            return ['-%s_%s' % (field, region.id)]
        return ['-%s' % field]

    def filter_queryset(self, request, queryset, view):

        region = get_region_from_request(request)
        search_query = request.GET.get('q')
        sort = request.GET.getlist('sort')

        # When querying (with `?q=`) we want to sort by relevance. If no query
        # is provided and no `?sort` is provided, i.e. we are only applying
        # filters which don't affect the relevance, we sort by popularity
        # descending.
        order_by = None
        if not search_query:
            order_by = self._get_regional_sort(region, 'popularity')

        if sort:
            if 'popularity' in sort:
                order_by = self._get_regional_sort(region, 'popularity')
            elif 'trending' in sort:
                order_by = self._get_regional_sort(region, 'trending')
            else:
                order_by = [self.DEFAULT_SORTING[name] for name in sort
                            if name in self.DEFAULT_SORTING]

        if order_by:
            return queryset.sort(*order_by)

        return queryset
