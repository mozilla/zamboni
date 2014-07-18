from datetime import datetime

from django.conf import settings
from django.core.urlresolvers import reverse

from rest_framework import serializers

import amo
import mkt
from amo.helpers import absolutify
from constants.applications import DEVICE_TYPES
from mkt.api.fields import ESTranslationSerializerField
from mkt.submit.serializers import SimplePreviewSerializer
from mkt.versions.models import Version
from mkt.webapps.models import Geodata, Preview, Webapp
from mkt.webapps.serializers import AppSerializer, SimpleAppSerializer
from mkt.webapps.utils import dehydrate_content_rating


class BaseESSerializer(serializers.ModelSerializer):
    """
    A base deserializer that handles ElasticSearch data for a specific model.
    When deserializing, an unbound instance of the model (as defined by
    fake_object) is populated with the ES data in order to work well with
    the parent model serializer (e.g., AppSerializer).
    """
    def __init__(self, *args, **kwargs):
        super(BaseESSerializer, self).__init__(*args, **kwargs)

        # Set all fields as read_only just in case.
        for field_name in self.fields:
            self.fields[field_name].read_only = True

        if getattr(self, 'context'):
            for field_name in self.fields:
                self.fields[field_name].context = self.context

    @property
    def data(self):
        """
        Returns the serialized data on the serializer.
        """
        if self._data is None:
            if self.many:
                self._data = [self.to_native(item) for item in self.object]
            else:
                self._data = self.to_native(self.object)
        return self._data

    def field_to_native(self, obj, field_name):
        # DRF's field_to_native calls .all(), which we want to avoid, so we
        # provide a simplified version that doesn't and just iterates on the
        # object list.
        if hasattr(obj, 'object_list'):
            return [self.to_native(item) for item in obj.object_list]
        return super(BaseESSerializer, self).field_to_native(obj, field_name)

    def to_native(self, data):
        data = (data._source if hasattr(data, '_source') else
                data.get('_source', data))
        obj = self.fake_object(data)
        return super(BaseESSerializer, self).to_native(obj)

    def fake_object(self, data):
        """
        Create a fake instance from ES data which serializer fields will source
        from.
        """
        raise NotImplementedError

    def _attach_fields(self, obj, data, field_names):
        """Attach fields to fake instance."""
        for field_name in field_names:
            setattr(obj, field_name, data.get(field_name))
        return obj

    def _attach_translations(self, obj, data, field_names):
        """Deserialize ES translation fields."""
        for field_name in field_names:
            ESTranslationSerializerField.attach_translations(
                obj, data, field_name)
        return obj


class ESAppSerializer(BaseESSerializer, AppSerializer):
    # Fields specific to search.
    absolute_url = serializers.SerializerMethodField('get_absolute_url')
    reviewed = serializers.DateField()

    # Override previews, because we don't need the full PreviewSerializer.
    previews = SimplePreviewSerializer(many=True, source='all_previews')

    # Override those, because we want a different source. Also, related fields
    # will call self.queryset early if they are not read_only, so force that.
    manifest_url = serializers.CharField(source='manifest_url')
    package_path = serializers.SerializerMethodField('get_package_path')

    # Override translations, because we want a different field.
    banner_message = ESTranslationSerializerField(
        source='geodata.banner_message')
    description = ESTranslationSerializerField()
    homepage = ESTranslationSerializerField()
    name = ESTranslationSerializerField()
    release_notes = ESTranslationSerializerField(source='release_notes')
    support_email = ESTranslationSerializerField()
    support_url = ESTranslationSerializerField()

    # Feed collection.
    group = ESTranslationSerializerField(required=False)

    class Meta(AppSerializer.Meta):
        fields = AppSerializer.Meta.fields + ['absolute_url', 'group',
                                              'reviewed']

    def __init__(self, *args, **kwargs):
        super(ESAppSerializer, self).__init__(*args, **kwargs)

        # Remove fields that we don't have in ES at the moment.
        self.fields.pop('upsold', None)

    def fake_object(self, data):
        """Create a fake instance of Webapp and related models from ES data."""
        is_packaged = data['app_type'] != amo.ADDON_WEBAPP_HOSTED
        is_privileged = data['app_type'] == amo.ADDON_WEBAPP_PRIVILEGED

        obj = Webapp(id=data['id'], app_slug=data['app_slug'],
                     is_packaged=is_packaged, type=amo.ADDON_WEBAPP,
                     icon_type='image/png')

        # Set relations and attributes we need on those relations.
        # The properties set on latest_version and current_version differ
        # because we are only setting what the serializer is going to need.
        # In particular, latest_version.is_privileged needs to be set because
        # it's used by obj.app_type_id.
        obj.listed_authors = []
        obj._current_version = Version()
        obj._current_version.addon = obj
        obj._current_version._developer_name = data['author']
        obj._current_version.supported_locales = data['supported_locales']
        obj._current_version.version = data['current_version']
        obj._latest_version = Version()
        obj._latest_version.is_privileged = is_privileged
        obj._geodata = Geodata()
        obj.all_previews = [Preview(id=p['id'], modified=p['modified'],
            filetype=p['filetype'], sizes=p.get('sizes', {}))
            for p in data['previews']]
        obj.categories = data['category']
        obj._device_types = [DEVICE_TYPES[d] for d in data['device']]

        # Set base attributes on the "fake" app using the data from ES.
        self._attach_fields(
            obj, data, ('created', 'modified', 'default_locale', 'icon_hash',
                        'is_escalated', 'is_offline', 'manifest_url',
                        'premium_type', 'regions', 'reviewed', 'status',
                        'weekly_downloads'))

        # Attach translations for all translated attributes.
        self._attach_translations(
            obj, data, ('name', 'description', 'homepage', 'release_notes',
                        'support_email', 'support_url'))
        if 'group_translations' in data:
            self._attach_translations(obj, data, ('group',))  # Feed group.
        self._attach_translations(obj._geodata, data, ('banner_message',))

        # Set attributes that have a different name in ES.
        obj.public_stats = data['has_public_stats']

        # Override obj.get_region() with a static list of regions generated
        # from the region_exclusions stored in ES.
        obj.get_regions = obj.get_regions(obj.get_region_ids(
            restofworld=True, excluded=data['region_exclusions']))

        # Some methods below will need the raw data from ES, put it on obj.
        obj.es_data = data

        return obj

    def get_content_ratings(self, obj):
        body = (mkt.regions.REGION_TO_RATINGS_BODY().get(
            self.context['request'].REGION.slug, 'generic'))
        prefix = 'has_%s' % body

        # Backwards incompat with old index.
        for i, desc in enumerate(obj.es_data.get('content_descriptors', [])):
            if desc.isupper():
                obj.es_data['content_descriptors'][i] = 'has_' + desc.lower()
        for i, inter in enumerate(obj.es_data.get('interactive_elements', [])):
            if inter.isupper():
                obj.es_data['interactive_elements'][i] = 'has_' + inter.lower()

        return {
            'body': body,
            'rating': dehydrate_content_rating(
                (obj.es_data.get('content_ratings') or {})
                .get(body)) or None,
            'descriptors': [key for key in
                            obj.es_data.get('content_descriptors', [])
                            if prefix in key],
            'descriptors_text': [mkt.iarc_mappings.REVERSE_DESCS[key] for key
                                 in obj.es_data.get('content_descriptors')
                                 if prefix in key],
            'interactives': obj.es_data.get('interactive_elements', []),
            'interactives_text': [mkt.iarc_mappings.REVERSE_INTERACTIVES[key]
                                  for key in
                                  obj.es_data.get('interactive_elements')]
        }

    def get_versions(self, obj):
        return dict((v['version'], v['resource_uri'])
                    for v in obj.es_data['versions'])

    def get_ratings_aggregates(self, obj):
        return obj.es_data.get('ratings', {})

    def get_upsell(self, obj):
        upsell = obj.es_data.get('upsell', False)
        if upsell:
            region_id = self.context['request'].REGION.id
            exclusions = upsell.get('region_exclusions')
            if exclusions is not None and region_id not in exclusions:
                upsell['resource_uri'] = reverse('app-detail',
                    kwargs={'pk': upsell['id']})
            else:
                upsell = False
        return upsell

    def get_absolute_url(self, obj):
        return absolutify(obj.get_absolute_url())

    def get_package_path(self, obj):
        return obj.es_data.get('package_path')

    def get_tags(self, obj):
        return obj.es_data['tags']


class SimpleESAppSerializer(ESAppSerializer):

    class Meta(SimpleAppSerializer.Meta):
        pass


class SuggestionsESAppSerializer(ESAppSerializer):
    icon = serializers.SerializerMethodField('get_icon')

    class Meta(ESAppSerializer.Meta):
        fields = ['name', 'description', 'absolute_url', 'icon']

    def get_icon(self, app):
        return app.get_icon_url(64)


class RocketbarESAppSerializer(serializers.Serializer):
    """Used by Firefox OS's Rocketbar apps viewer."""
    name = ESTranslationSerializerField()

    @property
    def data(self):
        if self._data is None:
            self._data = [self.to_native(o['payload']) for o in self.object]
        return self._data

    def to_native(self, obj):
        # fake_app is a fake instance because we need to access a couple
        # properties and methods on Webapp. It should never hit the database.
        self.fake_app = Webapp(
            id=obj['id'], icon_type='image/png', type=amo.ADDON_WEBAPP,
            default_locale=obj.get('default_locale', settings.LANGUAGE_CODE),
            icon_hash=obj.get('icon_hash'),
            modified=datetime.strptime(obj['modified'], '%Y-%m-%dT%H:%M:%S'))
        ESTranslationSerializerField.attach_translations(
            self.fake_app, obj, 'name')
        return {
            'name': self.fields['name'].field_to_native(self.fake_app, 'name'),
            'icon': self.fake_app.get_icon_url(64),
            'slug': obj['slug'],
            'manifest_url': obj['manifest_url'],
        }


class RocketbarESAppSerializerV2(AppSerializer, RocketbarESAppSerializer):
    """
    Replaced `icon` key with `icons` for various pixel sizes: 128, 64, 48, 32.
    """

    def to_native(self, obj):
        data = super(RocketbarESAppSerializerV2, self).to_native(obj)
        del data['icon']
        data['icons'] = self.get_icons(self.fake_app)
        return data
