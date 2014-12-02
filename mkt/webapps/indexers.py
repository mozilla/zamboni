import sys
from operator import attrgetter

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db.models import Min
from elasticsearch_dsl import F, filter as es_filter, query

import commonware.log

import amo
import mkt
from mkt.constants import APP_FEATURES
from mkt.constants.applications import DEVICE_GAIA
from mkt.features.utils import get_feature_profile
from mkt.prices.models import AddonPremium
from mkt.search.indexers import BaseIndexer
from mkt.search.utils import Search
from mkt.translations.models import attach_trans_dict
from mkt.translations.utils import to_language
from mkt.versions.models import Version


log = commonware.log.getLogger('z.addons')


class WebappIndexer(BaseIndexer):
    """
    Bunch of ES stuff for Webapp include mappings, indexing, search.
    """
    @classmethod
    def search(cls, using=None):
        """
        Returns a `Search` object.

        We override this to use our patched version which adds statsd timing.
        """
        return Search(using=using or cls.get_es(),
                      index=cls.get_index(),
                      doc_type=cls.get_mapping_type_name())

    @classmethod
    def get_mapping_type_name(cls):
        """
        Returns mapping type name which is used as the key in ES_INDEXES to
        determine which index to use.

        We override this because Webapp is a proxy model to Addon.
        """
        return 'webapp'

    @classmethod
    def get_model(cls):
        from mkt.webapps.models import Webapp
        return Webapp

    @classmethod
    def get_mapping(cls):
        doc_type = cls.get_mapping_type_name()

        def _locale_field_mapping(field, analyzer):
            get_analyzer = lambda a: (
                '%s_analyzer' % a if a in amo.STEMMER_MAP else a)
            return {'%s_%s' % (field, analyzer): {
                'type': 'string', 'analyzer': get_analyzer(analyzer)}}

        mapping = {
            doc_type: {
                # Disable _all field to reduce index size.
                '_all': {'enabled': False},
                'properties': {
                    # Add a boost field to enhance relevancy of a document.
                    # This is used during queries in a function scoring query.
                    'boost': {'type': 'long', 'doc_values': True},
                    # App fields.
                    'id': {'type': 'long'},
                    'app_slug': {'type': 'string'},
                    'app_type': {'type': 'byte'},
                    'author': {
                        'type': 'string',
                        'analyzer': 'default_icu',
                        'fields': {
                            # For exact matches. The simple analyzer allows
                            # for case-insensitive matching.
                            'raw': {'type': 'string',
                                    'analyzer': 'exact_lowercase'},
                        },
                    },
                    'banner_regions': cls.string_not_indexed(),
                    'bayesian_rating': {'type': 'float', 'doc_values': True},
                    'category': cls.string_not_analyzed(),
                    'content_descriptors': cls.string_not_indexed(),
                    'content_ratings': {
                        'type': 'object',
                        'dynamic': 'true',
                    },
                    'created': {'format': 'dateOptionalTime', 'type': 'date',
                                'doc_values': True},
                    'current_version': cls.string_not_indexed(),
                    'default_locale': cls.string_not_indexed(),
                    'description': {'type': 'string',
                                    'analyzer': 'default_icu'},
                    'device': {'type': 'byte'},
                    'features': {
                        'type': 'object',
                        'properties': dict(
                            ('has_%s' % f.lower(), {'type': 'boolean'})
                            for f in APP_FEATURES)
                    },
                    'has_public_stats': {'type': 'boolean'},
                    'icon_hash': cls.string_not_indexed(),
                    'interactive_elements': cls.string_not_indexed(),
                    'installs_allowed_from': cls.string_not_analyzed(),
                    'is_disabled': {'type': 'boolean'},
                    'is_escalated': {'type': 'boolean'},
                    'is_offline': {'type': 'boolean'},
                    'is_priority': {'type': 'boolean'},
                    'is_rereviewed': {'type': 'boolean'},
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'latest_version': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'byte'},
                            'is_privileged': {'type': 'boolean'},
                            'has_editor_comment': {'type': 'boolean'},
                            'has_info_request': {'type': 'boolean'},
                            'nomination_date': {'type': 'date',
                                                'format': 'dateOptionalTime'},
                            'created_date': {'type': 'date',
                                             'format': 'dateOptionalTime'},
                        },
                    },
                    'manifest_url': cls.string_not_analyzed(),
                    'modified': {'format': 'dateOptionalTime',
                                 'type': 'date'},
                    # Name for searching.
                    'name': {'type': 'string', 'analyzer': 'default_icu'},
                    # Name for sorting.
                    'name_sort': cls.string_not_analyzed(doc_values=True),
                    # Name for suggestions.
                    'name_suggest': {'type': 'completion', 'payloads': True},
                    'owners': {'type': 'long'},
                    'package_path': cls.string_not_indexed(),
                    'popularity': {'type': 'long', 'doc_values': True},
                    'premium_type': {'type': 'byte'},
                    'previews': {
                        'type': 'object',
                        'dynamic': 'true',
                    },
                    'price_tier': cls.string_not_indexed(),
                    'ratings': {
                        'type': 'object',
                        'properties': {
                            'average': {'type': 'float'},
                            'count': {'type': 'short'},
                        }
                    },
                    'region_exclusions': {'type': 'short'},
                    'reviewed': {'format': 'dateOptionalTime', 'type': 'date',
                                 'doc_values': True},
                    'status': {'type': 'byte'},
                    'supported_locales': cls.string_not_analyzed(),
                    'tags': {'type': 'string', 'analyzer': 'simple'},
                    'upsell': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'long'},
                            'app_slug': cls.string_not_indexed(),
                            'icon_url': cls.string_not_indexed(),
                            'name': cls.string_not_indexed(),
                            'region_exclusions': {'type': 'short'},
                        }
                    },
                    'uses_flash': {'type': 'boolean'},
                    'versions': {
                        'type': 'object',
                        'properties': {
                            'version': cls.string_not_indexed(),
                            'resource_uri': cls.string_not_indexed(),
                        }
                    },
                    'weekly_downloads': {'type': 'long', 'doc_values': True},
                }
            }
        }

        # Add popularity by region.
        for region in mkt.regions.ALL_REGION_IDS:
            mapping[doc_type]['properties'].update(
                {'popularity_%s' % region: {'type': 'long'}})

        # Add fields that we expect to return all translations.
        cls.attach_translation_mappings(
            mapping, ('banner_message', 'description', 'homepage',
                      'name', 'release_notes', 'support_email',
                      'support_url'))

        # Add room for language-specific indexes.
        for analyzer in amo.SEARCH_ANALYZER_MAP:
            if (not settings.ES_USE_PLUGINS and
                analyzer in amo.SEARCH_ANALYZER_PLUGINS):
                log.info('While creating mapping, skipping the %s analyzer'
                         % analyzer)
                continue

            mapping[doc_type]['properties'].update(
                _locale_field_mapping('name', analyzer))
            mapping[doc_type]['properties'].update(
                _locale_field_mapping('description', analyzer))

        return mapping

    @classmethod
    def extract_document(cls, pk=None, obj=None):
        """Extracts the ElasticSearch index document for this instance."""
        from mkt.webapps.models import (AppFeatures, attach_devices,
                                        attach_prices, attach_tags,
                                        attach_translations, Geodata,
                                        Installed, RatingDescriptors,
                                        RatingInteractives)

        if obj is None:
            obj = cls.get_model().objects.no_cache().get(pk=pk)

        # Attach everything we need to index apps.
        for transform in (attach_devices, attach_prices, attach_tags,
                          attach_translations):
            transform([obj])

        latest_version = obj.latest_version
        version = obj.current_version
        geodata = obj.geodata
        features = (version.features.to_dict()
                    if version else AppFeatures().to_dict())

        try:
            status = latest_version.statuses[0][1] if latest_version else None
        except IndexError:
            status = None

        installed_ids = list(Installed.objects.filter(addon=obj)
                             .values_list('id', flat=True))

        attrs = ('app_slug', 'bayesian_rating', 'created', 'id', 'is_disabled',
                 'last_updated', 'modified', 'premium_type', 'status',
                 'uses_flash', 'weekly_downloads')
        d = dict(zip(attrs, attrgetter(*attrs)(obj)))

        d['boost'] = len(installed_ids) or 1
        d['app_type'] = obj.app_type_id
        d['author'] = obj.developer_name
        d['banner_regions'] = geodata.banner_regions_slugs()
        d['category'] = obj.categories if obj.categories else []
        d['content_ratings'] = (obj.get_content_ratings_by_body(es=True) or
                                None)
        try:
            d['content_descriptors'] = obj.rating_descriptors.to_keys()
        except RatingDescriptors.DoesNotExist:
            d['content_descriptors'] = []
        d['current_version'] = version.version if version else None
        d['default_locale'] = obj.default_locale
        d['description'] = list(
            set(string for _, string in obj.translations[obj.description_id]))
        d['device'] = getattr(obj, 'device_ids', [])
        d['features'] = features
        d['has_public_stats'] = obj.public_stats
        d['icon_hash'] = obj.icon_hash
        try:
            d['interactive_elements'] = obj.rating_interactives.to_keys()
        except RatingInteractives.DoesNotExist:
            d['interactive_elements'] = []
        d['installs_allowed_from'] = (
            version.manifest.get('installs_allowed_from', ['*'])
            if version else ['*'])
        d['is_escalated'] = obj.escalationqueue_set.exists()
        d['is_offline'] = getattr(obj, 'is_offline', False)
        d['is_priority'] = obj.priority_review
        d['is_rereviewed'] = obj.rereviewqueue_set.exists()
        if latest_version:
            d['latest_version'] = {
                'status': status,
                'is_privileged': latest_version.is_privileged,
                'has_editor_comment': latest_version.has_editor_comment,
                'has_info_request': latest_version.has_info_request,
                'nomination_date': latest_version.nomination,
                'created_date': latest_version.created,
            }
        else:
            d['latest_version'] = {
                'status': None,
                'is_privileged': None,
                'has_editor_comment': None,
                'has_info_request': None,
                'nomination_date': None,
                'created_date': None,
            }
        d['manifest_url'] = obj.get_manifest_url()
        d['package_path'] = obj.get_package_path()
        d['name'] = list(
            set(string for _, string in obj.translations[obj.name_id]))
        d['name_sort'] = unicode(obj.name).lower()
        d['owners'] = [au.user.id for au in
                       obj.addonuser_set.filter(role=amo.AUTHOR_ROLE_OWNER)]
        d['popularity'] = len(installed_ids)
        d['previews'] = [{'filetype': p.filetype, 'modified': p.modified,
                          'id': p.id, 'sizes': p.sizes}
                         for p in obj.previews.all()]
        try:
            p = obj.addonpremium.price
            d['price_tier'] = p.name
        except AddonPremium.DoesNotExist:
            d['price_tier'] = None

        d['ratings'] = {
            'average': obj.average_rating,
            'count': obj.total_reviews,
        }
        d['region_exclusions'] = obj.get_excluded_region_ids()
        d['reviewed'] = obj.versions.filter(
            deleted=False).aggregate(Min('reviewed')).get('reviewed__min')
        if version:
            d['supported_locales'] = filter(
                None, version.supported_locales.split(','))
        else:
            d['supported_locales'] = []

        d['tags'] = getattr(obj, 'tag_list', [])
        if obj.upsell and obj.upsell.premium.is_published():
            upsell_obj = obj.upsell.premium
            d['upsell'] = {
                'id': upsell_obj.id,
                'app_slug': upsell_obj.app_slug,
                'icon_url': upsell_obj.get_icon_url(128),
                # TODO: Store all localizations of upsell.name.
                'name': unicode(upsell_obj.name),
                'region_exclusions': upsell_obj.get_excluded_region_ids()
            }

        d['versions'] = [dict(version=v.version,
                              resource_uri=reverse_version(v))
                         for v in obj.versions.all()]

        # Handle our localized fields.
        for field in ('description', 'homepage', 'name', 'support_email',
                      'support_url'):
            d['%s_translations' % field] = [
                {'lang': to_language(lang), 'string': string}
                for lang, string
                in obj.translations[getattr(obj, '%s_id' % field)]
                if string]
        if version:
            attach_trans_dict(Version, [version])
            d['release_notes_translations'] = [
                {'lang': to_language(lang), 'string': string}
                for lang, string
                in version.translations[version.releasenotes_id]]
        else:
            d['release_notes_translations'] = None
        attach_trans_dict(Geodata, [geodata])
        d['banner_message_translations'] = [
            {'lang': to_language(lang), 'string': string}
            for lang, string
            in geodata.translations[geodata.banner_message_id]]

        for region in mkt.regions.ALL_REGION_IDS:
            d['popularity_%s' % region] = d['popularity']

        # Bump the boost if the add-on is public.
        if obj.status == amo.STATUS_PUBLIC:
            d['boost'] = max(d['boost'], 1) * 4

        # If the app is compatible with Firefox OS, push suggestion data in the
        # index - This will be used by RocketbarView API, which is specific to
        # Firefox OS.
        if DEVICE_GAIA.id in d['device'] and obj.is_published():
            d['name_suggest'] = {
                'input': d['name'],
                'output': unicode(obj.id),  # We only care about the payload.
                'weight': d['boost'],
                'payload': {
                    'default_locale': d['default_locale'],
                    'icon_hash': d['icon_hash'],
                    'id': d['id'],
                    'manifest_url': d['manifest_url'],
                    'modified': d['modified'],
                    'name_translations': d['name_translations'],
                    'slug': d['app_slug'],
                }
            }

        # Indices for each language. languages is a list of locales we want to
        # index with analyzer if the string's locale matches.
        for analyzer, languages in amo.SEARCH_ANALYZER_MAP.iteritems():
            if (not settings.ES_USE_PLUGINS and
                analyzer in amo.SEARCH_ANALYZER_PLUGINS):
                continue

            d['name_' + analyzer] = list(
                set(string for locale, string in obj.translations[obj.name_id]
                    if locale.lower() in languages))
            d['description_' + analyzer] = list(
                set(string for locale, string
                    in obj.translations[obj.description_id]
                    if locale.lower() in languages))

        return d

    @classmethod
    def get_indexable(cls):
        """Returns the queryset of ids of all things to be indexed."""
        from mkt.webapps.models import Webapp
        return Webapp.with_deleted.all()

    @classmethod
    def run_indexing(cls, ids, ES, index=None, **kw):
        """Override run_indexing to use app transformers."""
        from mkt.webapps.models import Webapp
        sys.stdout.write('Indexing %s webapps\n' % len(ids))

        qs = Webapp.with_deleted.no_cache().filter(id__in=ids)

        docs = []
        for obj in qs:
            try:
                docs.append(cls.extract_document(obj.id, obj=obj))
            except Exception as e:
                sys.stdout.write('Failed to index webapp {0}: {1}\n'.format(
                    obj.id, e))

        cls.bulk_index(docs, es=ES, index=index or cls.get_index())

    @classmethod
    def get_app_filter(cls, request, additional_data=None, sq=None,
                       app_ids=None, no_filter=False):
        """
        THE grand, consolidated ES filter for Webapps. By default:
        - Excludes non-public apps.
        - Excludes disabled apps (whether by reviewer or by developer).
        - Excludes based on region exclusions.

        additional_data -- an object with more data to allow more filtering.
        sq -- if you have an existing search object to filter off of.
        app_ids -- if you want to filter by a list of app IDs.
        no_filter -- doesn't apply the consumer-side excludes (public/region).
        """
        from mkt.api.base import get_region_from_request
        from mkt.search.views import name_query

        sq = sq or cls.search()
        additional_data = additional_data or {}
        app_ids = app_ids or []

        data = {
            'app_type': [],
            'author.raw': None,
            'category': None,  # Slug.
            'device': None,  # ID.
            'gaia': getattr(request, 'GAIA', False),
            'installs_allowed_from': None,
            'is_offline': None,
            'manifest_url': '',
            'mobile': getattr(request, 'MOBILE', False),
            'premium_type': [],
            'profile': get_feature_profile(request),
            'q': '',
            'region': getattr(get_region_from_request(request), 'id', None),
            'status': None,
            'supported_locales': [],
            'tablet': getattr(request, 'TABLET', False),
            'tags': '',
        }
        data.update(additional_data)

        # Fields that will be filtered with a term query.
        term_fields = ('author.raw', 'device', 'installs_allowed_from',
                       'manifest_url', 'status', 'tags')
        # Fields that will be filtered with a terms query.
        terms_fields = ('category', 'premium_type', 'app_type',
                        'supported_locales')

        # QUERY.
        if data['q']:
            # Function score for popularity boosting (defaults to multiply).
            sq = sq.query(
                'function_score',
                query=name_query(data['q'].lower()),
                functions=[query.SF('field_value_factor', field='boost')])

        # MUST.
        must = [
            F('term', status=amo.STATUS_PUBLIC),
            F('term', is_disabled=False),
        ] if not no_filter else []

        for field in term_fields + terms_fields:
            # Term filters.
            if data[field]:
                filter_type = 'term' if field in term_fields else 'terms'
                must.append(F(filter_type, **{field: data[field]}))

        if not no_filter:
            if data['profile']:
                # Feature filters.
                profile = data['profile']
                for k, v in profile.to_kwargs(prefix='features.has_').items():
                    must.append(F('term', **{k: v}))
            if data['mobile'] or data['gaia']:
                # Uses flash.
                must.append(F('term', uses_flash=False))
            if data['is_offline'] is not None:
                must.append(F('term', is_offline=data['is_offline']))

        # SHOULD.
        should = []
        if app_ids:
            should = [es_filter.Terms(id=list(set(app_ids)))]
            sq = sq[0:len(set(app_ids))]

        # FILTER.
        if must or should:
            sq = sq.filter(es_filter.Bool(must=must, should=should))

        if data['region'] and not no_filter:
            # Region exclusions.
            sq = sq.filter(~F('term', region_exclusions=data['region']))

        return sq


def reverse_version(version):
    """
    The try/except AttributeError allows this to be used where the input is
    ambiguous, and could be either an already-reversed URL or a Version object.
    """
    if version:
        try:
            return reverse('version-detail', kwargs={'pk': version.pk})
        except AttributeError:
            return version
    return
