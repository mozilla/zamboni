from drf_compound_fields.fields import ListField
from rest_framework.fields import CharField, SerializerMethodField
from rest_framework.serializers import ModelSerializer

from mkt.api.fields import ReverseChoiceField, TranslationSerializerField
from mkt.constants.base import (STATUS_CHOICES_API_v2,
                                STATUS_FILE_CHOICES_API_v2, STATUS_PUBLIC)
from mkt.extensions.models import Extension, ExtensionVersion
from mkt.search.serializers import BaseESSerializer


class ExtensionVersionSerializer(ModelSerializer):
    download_url = CharField(source='download_url', read_only=True)
    unsigned_download_url = CharField(
        source='unsigned_download_url', read_only=True)
    reviewer_mini_manifest_url = CharField(
        source='reviewer_mini_manifest_url', read_only=True)
    status = ReverseChoiceField(
        choices_dict=STATUS_FILE_CHOICES_API_v2, read_only=True)

    class Meta:
        model = ExtensionVersion
        fields = ['id', 'created', 'download_url',
                  'reviewer_mini_manifest_url', 'unsigned_download_url',
                  'size', 'status', 'version']


class ExtensionSerializer(ModelSerializer):
    description = TranslationSerializerField(read_only=True)
    device_types = ListField(CharField(), source='device_names')
    icons = SerializerMethodField('get_icons')
    latest_public_version = ExtensionVersionSerializer(
        source='latest_public_version', read_only=True)
    latest_version = ExtensionVersionSerializer(
        source='latest_version', read_only=True)
    mini_manifest_url = CharField(source='mini_manifest_url', read_only=True)
    name = TranslationSerializerField(read_only=True)
    status = ReverseChoiceField(
        choices_dict=STATUS_CHOICES_API_v2, read_only=True)

    # FIXME: latest_version potentially expose private data.
    # Nothing extremely major, but maybe we care. Not a fan of moving it to
    # another endpoint since that'd mean developers and reviewers would need
    # to use that other endpoint instead of the regular one, but maybe that's
    # the way to go ? That endpoint could include all versions info, too.

    def get_icons(self, obj):
        return {size: obj.get_icon_url(size) for size in (64, 128)}

    class Meta:
        model = Extension
        fields = ['id', 'author', 'description', 'device_types', 'disabled',
                  'icons', 'last_updated', 'latest_version',
                  'latest_public_version', 'mini_manifest_url', 'name', 'slug',
                  'status', 'uuid', ]


class ESExtensionSerializer(BaseESSerializer, ExtensionSerializer):
    class Meta(ExtensionSerializer.Meta):
        # Exclude non-public version data that we don't currently store in ES.
        exclude = ['latest_version', 'versions', ]

    def fake_object(self, data):
        """Create a fake instance of Extension from ES data."""
        obj = Extension(id=data['id'])

        # Create a fake ExtensionVersion for latest_public_version.
        if data['latest_public_version']:
            obj.latest_public_version = ExtensionVersion(
                extension=obj,
                id=data['latest_public_version']['id'],
                created=data['latest_public_version']['created'],
                size=data['latest_public_version'].get('size', 0),
                status=STATUS_PUBLIC,
                version=data['latest_public_version']['version'],)

        # Set basic attributes we'll need on the fake instance using the data
        # from ES.
        self._attach_fields(
            obj, data, ('author', 'created', 'default_language', 'icon_hash',
                        'last_updated', 'modified', 'slug', 'status',
                        'version'))

        obj.deleted = data['is_deleted']
        obj.disabled = data['is_disabled']
        obj.uuid = data['guid']

        # Attach translations for all translated attributes.
        # obj.default_language should be set first for this to work.
        self._attach_translations(
            obj, data, ('name', 'description', ))

        # Some methods might need the raw data from ES, put it on obj.
        obj.es_data = data

        return obj
