from rest_framework import serializers

import mkt
from mkt.constants.base import CONTENT_ICON_SIZES
from mkt.api.fields import (GuessLanguageTranslationField,
                            TranslationSerializerField)
from mkt.search.serializers import BaseESSerializer
from mkt.tags.models import attach_tags
from mkt.websites.models import Website, WebsiteSubmission


class WebsiteSerializer(serializers.ModelSerializer):
    categories = serializers.ListField(child=serializers.CharField())
    description = TranslationSerializerField()
    device_types = serializers.ListField(serializers.CharField(),
                                         source='device_names')
    icons = serializers.SerializerMethodField()
    id = serializers.IntegerField(source='pk')
    keywords = serializers.SerializerMethodField()
    name = TranslationSerializerField()
    promo_imgs = serializers.SerializerMethodField()
    short_name = TranslationSerializerField()
    developer_name = TranslationSerializerField(required=False)
    title = TranslationSerializerField()

    class Meta:
        model = Website
        fields = ['categories', 'description', 'device_types',
                  'developer_name', 'icons', 'id', 'keywords', 'mobile_url',
                  'name', 'promo_imgs', 'short_name', 'title', 'url']

    def get_icons(self, obj):
        return {icon_size: obj.get_icon_url(icon_size)
                for icon_size in CONTENT_ICON_SIZES}

    def get_keywords(self, obj):
        if not hasattr(obj, 'keywords_list'):
            attach_tags([obj])
        return getattr(obj, 'keywords_list', [])

    def get_promo_imgs(self, obj):
        return dict([(promo_img_size, obj.get_promo_img_url(promo_img_size))
                     for promo_img_size in mkt.PROMO_IMG_SIZES])


class ESWebsiteSerializer(BaseESSerializer, WebsiteSerializer):
    def fake_object(self, data):
        """Create a fake instance of Website from ES data."""
        obj = Website(id=data['id'])

        # Set basic attributes on the fake instance using the data from ES.
        self._attach_fields(
            obj, data, ('default_locale', 'icon_hash', 'mobile_url',
                        'promo_img_hash', 'tv_featured', 'tv_url', 'url'))

        # Set attributes with names that don't exactly match the one on the
        # model.
        obj.categories = data['category']
        obj.devices = data['device']
        obj.keywords_list = data['tags']

        if obj.icon_hash:
            # If we have an icon_hash, then we have an icon. All the icons we
            # store are PNGs.
            obj.icon_type = 'image/png'

        # Attach translations for all translated attributes. obj.default_locale
        # should be set first for this to work.
        self._attach_translations(
            obj, data, ('description', 'developer_name', 'name', 'short_name',
                        'title'))

        # Some methods might need the raw data from ES, put it on obj.
        obj.es_data = data

        return obj


class ReviewerESWebsiteSerializer(ESWebsiteSerializer):
    class Meta(ESWebsiteSerializer.Meta):
        model = Website
        fields = ESWebsiteSerializer.Meta.fields + ['status']


class PublicWebsiteSubmissionSerializer(serializers.ModelSerializer):
    categories = serializers.ListField(child=serializers.CharField())
    description = GuessLanguageTranslationField()
    id = serializers.IntegerField(source='pk', required=False)
    keywords = serializers.ListField(child=serializers.CharField())
    name = GuessLanguageTranslationField()
    preferred_regions = serializers.ListField(
        child=serializers.CharField(), required=False)
    works_well = serializers.IntegerField()

    class Meta:
        model = WebsiteSubmission
        fields = ['canonical_url', 'categories', 'description',
                  'detected_icon', 'id', 'keywords', 'name',
                  'preferred_regions', 'public_credit', 'url', 'why_relevant',
                  'works_well']
