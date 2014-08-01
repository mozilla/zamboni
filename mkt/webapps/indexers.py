import math
import sys
from operator import attrgetter

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db.models import Max, Min

import commonware.log

import amo
import mkt
from amo.utils import to_language
from mkt.constants import APP_FEATURES
from mkt.constants.applications import DEVICE_GAIA
from mkt.prices.models import AddonPremium
from mkt.search.indexers import BaseIndexer
from mkt.versions.models import Version


log = commonware.log.getLogger('z.addons')


class WebappIndexer(BaseIndexer):
    """
    Mapping type for Webapp models.

    By default we will return these objects rather than hit the database so
    include here all the things we need to avoid hitting the database.
    """

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
                    'boost': {'type': 'long'},
                    # App fields.
                    'id': {'type': 'long'},
                    'app_slug': {'type': 'string'},
                    'app_type': {'type': 'byte'},
                    'author': {'type': 'string'},
                    'banner_regions': {
                        'type': 'string',
                        'index': 'not_analyzed'
                    },
                    'bayesian_rating': {'type': 'float'},
                    'category': {
                        'type': 'string',
                        'index': 'not_analyzed'
                    },
                    'collection': {
                        'type': 'nested',
                        'include_in_parent': True,
                        'properties': {
                            'id': {'type': 'long'},
                            'order': {'type': 'short'}
                        }
                    },
                    'content_descriptors': {
                        'type': 'string',
                        'index': 'not_analyzed'
                    },
                    'content_ratings': {
                        'type': 'object',
                        'dynamic': 'true',
                    },
                    'created': {'format': 'dateOptionalTime', 'type': 'date'},
                    'current_version': {'type': 'string',
                                        'index': 'not_analyzed'},
                    'default_locale': {'type': 'string',
                                       'index': 'not_analyzed'},
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
                    'icon_hash': {'type': 'string',
                                  'index': 'not_analyzed'},
                    'interactive_elements': {
                        'type': 'string',
                        'index': 'not_analyzed'
                    },
                    'is_disabled': {'type': 'boolean'},
                    'is_escalated': {'type': 'boolean'},
                    'is_offline': {'type': 'boolean'},
                    'last_updated': {'format': 'dateOptionalTime',
                                     'type': 'date'},
                    'latest_version': {
                        'type': 'object',
                        'properties': {
                            'status': {'type': 'byte'},
                            'is_privileged': {'type': 'boolean'},
                            'has_editor_comment': {'type': 'boolean'},
                            'has_info_request': {'type': 'boolean'},
                        },
                    },
                    'manifest_url': {'type': 'string',
                                     'index': 'not_analyzed'},
                    'modified': {'format': 'dateOptionalTime',
                                 'type': 'date',
                                 'index': 'not_analyzed'},
                    # Name for searching.
                    'name': {'type': 'string', 'analyzer': 'default_icu'},
                    # Name for sorting.
                    'name_sort': {'type': 'string', 'index': 'not_analyzed'},
                    # Name for suggestions.
                    'name_suggest': {'type': 'completion', 'payloads': True},
                    'owners': {'type': 'long'},
                    'package_path': {'type': 'string',
                                     'index': 'not_analyzed'},
                    'popularity': {'type': 'long'},
                    'premium_type': {'type': 'byte'},
                    'previews': {
                        'type': 'object',
                        'dynamic': 'true',
                    },
                    'price_tier': {'type': 'string',
                                   'index': 'not_analyzed'},
                    'ratings': {
                        'type': 'object',
                        'properties': {
                            'average': {'type': 'float'},
                            'count': {'type': 'short'},
                        }
                    },
                    'region_exclusions': {'type': 'short'},
                    'reviewed': {'format': 'dateOptionalTime', 'type': 'date'},
                    'status': {'type': 'byte'},
                    'supported_locales': {'type': 'string',
                                          'index': 'not_analyzed'},
                    'tags': {'type': 'string', 'analyzer': 'simple'},
                    'type': {'type': 'byte'},
                    'upsell': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'long'},
                            'app_slug': {'type': 'string',
                                         'index': 'not_analyzed'},
                            'icon_url': {'type': 'string',
                                         'index': 'not_analyzed'},
                            'name': {'type': 'string',
                                     'index': 'not_analyzed'},
                            'region_exclusions': {'type': 'short'},
                        }
                    },
                    'uses_flash': {'type': 'boolean'},
                    'versions': {
                        'type': 'object',
                        'properties': {
                            'version': {'type': 'string',
                                        'index': 'not_analyzed'},
                            'resource_uri': {'type': 'string',
                                             'index': 'not_analyzed'},
                        }
                    },
                    'weekly_downloads': {'type': 'long'},
                    'weight': {'type': 'short'},
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
                                        RatingInteractives, Webapp)

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
        is_escalated = obj.escalationqueue_set.exists()

        try:
            status = latest_version.statuses[0][1] if latest_version else None
        except IndexError:
            status = None

        installed_ids = list(Installed.objects.filter(addon=obj)
                             .values_list('id', flat=True))

        attrs = ('app_slug', 'bayesian_rating', 'created', 'id', 'is_disabled',
                 'last_updated', 'modified', 'premium_type', 'status', 'type',
                 'uses_flash', 'weekly_downloads')
        d = dict(zip(attrs, attrgetter(*attrs)(obj)))

        d['boost'] = len(installed_ids) or 1
        d['app_type'] = obj.app_type_id
        d['author'] = obj.developer_name
        d['banner_regions'] = geodata.banner_regions_slugs()
        d['category'] = obj.categories if obj.categories else []
        if obj.is_public:
            d['collection'] = [{'id': cms.collection_id, 'order': cms.order}
                               for cms in obj.collectionmembership_set.all()]
        else:
            d['collection'] = []
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
        d['is_escalated'] = is_escalated
        d['is_offline'] = getattr(obj, 'is_offline', False)
        if latest_version:
            d['latest_version'] = {
                'status': status,
                'is_privileged': latest_version.is_privileged,
                'has_editor_comment': latest_version.has_editor_comment,
                'has_info_request': latest_version.has_info_request,
            }
        else:
            d['latest_version'] = {
                'status': None,
                'is_privileged': None,
                'has_editor_comment': None,
                'has_info_request': None,
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
        if obj.upsell and obj.upsell.premium.is_public():
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

        # Calculate weight. It's similar to popularity, except that we can
        # expose the number - it's relative to the max weekly downloads for
        # the whole database.
        max_downloads = float(
            Webapp.objects.aggregate(Max('weekly_downloads')).values()[0] or 0)
        if max_downloads:
            d['weight'] = math.ceil(d['weekly_downloads'] / max_downloads * 5)
        else:
            d['weight'] = 1

        # Handle our localized fields.
        for field in ('description', 'homepage', 'name', 'support_email',
                      'support_url'):
            d['%s_translations' % field] = [
                {'lang': to_language(lang), 'string': string}
                for lang, string
                in obj.translations[getattr(obj, '%s_id' % field)]
                if string]
        if version:
            amo.utils.attach_trans_dict(Version, [version])
            d['release_notes_translations'] = [
                {'lang': to_language(lang), 'string': string}
                for lang, string
                in version.translations[version.releasenotes_id]]
        else:
            d['release_notes_translations'] = None
        amo.utils.attach_trans_dict(Geodata, [geodata])
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
        if DEVICE_GAIA.id in d['device'] and obj.is_public():
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

        WebappIndexer.bulk_index(docs, es=ES, index=index or cls.get_index())


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
