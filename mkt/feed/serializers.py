from django.conf import settings

from rest_framework import relations, serializers
from rest_framework.reverse import reverse

import mkt.carriers
import mkt.regions
from mkt.api.fields import SplitField, TranslationSerializerField
from mkt.api.serializers import URLSerializerMixin
from mkt.collections.serializers import (SlugChoiceField, SlugModelChoiceField)
from mkt.submit.serializers import PreviewSerializer
from mkt.webapps.serializers import AppSerializer

import amo
from addons.models import Category

from . import constants
from .fields import FeedCollectionMembershipField
from .models import (FeedApp, FeedBrand, FeedCollection,
                     FeedCollectionMembership, FeedItem)


class BaseFeedCollectionSerializer(URLSerializerMixin,
                                   serializers.ModelSerializer):
    """
    Base serializer for subclasses of BaseFeedCollection.
    """
    apps = FeedCollectionMembershipField(many=True, source='apps')
    slug = serializers.CharField(required=False)

    class Meta:
        fields = ('apps', 'slug', 'url')


class FeedImageField(serializers.HyperlinkedRelatedField):
    read_only = True

    def get_url(self, obj, view_name, request, format):
        if obj.has_image:
            # Always prefix with STATIC_URL to return images from our CDN.
            prefix = settings.STATIC_URL.strip('/')
            # Always append image_hash so that we can send far-future expires.
            suffix = '?%s' % obj.image_hash
            url = reverse(view_name, kwargs={'pk': obj.pk}, request=request,
                          format=format)
            return '%s%s%s' % (prefix, url, suffix)
        else:
            return None


class FeedAppSerializer(URLSerializerMixin, serializers.ModelSerializer):
    """
    A serializer for the FeedApp class, which highlights a single app and some
    additional metadata (e.g. a review or a screenshot).
    """
    app = SplitField(relations.PrimaryKeyRelatedField(required=True),
                     AppSerializer())
    description = TranslationSerializerField(required=False)
    background_image = FeedImageField(
        source='*', view_name='api-v2:feed-app-image-detail', format='png')
    preview = SplitField(relations.PrimaryKeyRelatedField(required=False),
                         PreviewSerializer())
    pullquote_rating = serializers.IntegerField(required=False)
    pullquote_text = TranslationSerializerField(required=False)

    class Meta:
        fields = ('app', 'background_color', 'background_image', 'created',
                  'description', 'id', 'preview', 'pullquote_attribution',
                  'pullquote_rating', 'pullquote_text', 'slug', 'type',
                  'url')
        model = FeedApp
        url_basename = 'feedapps'


class FeedBrandSerializer(BaseFeedCollectionSerializer):
    """
    A serializer for the FeedBrand class, a type of collection that allows
    editors to quickly create content without involving localizers.
    """
    layout = serializers.ChoiceField(choices=constants.BRAND_LAYOUT_CHOICES,
                                     required=True)
    type = serializers.ChoiceField(choices=constants.BRAND_TYPE_CHOICES,
                                   required=True)

    class Meta:
        fields = ('apps', 'id', 'layout', 'slug', 'type', 'url')
        model = FeedBrand
        url_basename = 'feedbrands'


class FeedCollectionSerializer(BaseFeedCollectionSerializer):
    """
    A serializer for the FeedCollection class.
    """
    type = serializers.ChoiceField(choices=constants.COLLECTION_TYPE_CHOICES)
    background_color = serializers.CharField(max_length=7, required=False)
    background_image = FeedImageField(
        source='*', view_name='api-v2:feed-collection-image-detail',
        format='png')
    description = TranslationSerializerField(required=False)
    name = TranslationSerializerField()
    apps = serializers.SerializerMethodField('get_apps')

    class Meta:
        fields = ('apps', 'background_color', 'background_image',
                  'description', 'id', 'name', 'slug', 'type', 'url')
        model = FeedCollection
        url_basename = 'feedcollections'

    def validate_background_color(self, attrs, source):
        background_color = attrs.get(source, None)
        if (attrs.get('type') == constants.COLLECTION_TYPE_PROMO and not
            background_color):
            raise serializers.ValidationError(
                '`background_color` is required for `promo` collections.'
            )
        return attrs

    def get_apps(self, obj):
        """
        Return a list of serialized apps, adding each app's `group` to the
        serialization.
        """
        ret = []
        memberships = FeedCollectionMembership.objects.filter(obj=self.object)
        field = TranslationSerializerField()
        field.initialize(self, 'group')
        field.context = self.context
        for member in memberships:
            data = AppSerializer(member.app).data
            data['group'] = field.field_to_native(member, 'group')
            ret.append(data)
        return ret


class FeedItemSerializer(URLSerializerMixin, serializers.ModelSerializer):
    """
    A serializer for the FeedItem class, which wraps all items that live on the
    feed.
    """
    carrier = SlugChoiceField(required=False,
        choices_dict=mkt.carriers.CARRIER_MAP)
    region = SlugChoiceField(required=False,
        choices_dict=mkt.regions.REGION_LOOKUP)
    category = SlugModelChoiceField(required=False,
        queryset=Category.objects.filter(type=amo.ADDON_WEBAPP))
    item_type = serializers.SerializerMethodField('get_item_type')

    # Types of objects that are allowed to be a feed item.
    app = SplitField(relations.PrimaryKeyRelatedField(required=False),
                     FeedAppSerializer())
    brand = SplitField(relations.PrimaryKeyRelatedField(required=False),
                       FeedBrandSerializer())
    collection = SplitField(relations.PrimaryKeyRelatedField(required=False),
                            FeedCollectionSerializer())

    class Meta:
        fields = ('app', 'brand', 'carrier', 'category', 'collection', 'id',
                  'item_type', 'region', 'url')
        item_types = ('app', 'brand', 'collection')
        model = FeedItem
        url_basename = 'feeditems'

    def validate(self, attrs):
        """
        Ensure that at least one object type is specified.
        """
        item_changed = any(k for k in self.Meta.item_types
                           if k in attrs.keys())
        num_defined = sum(1 for item in self.Meta.item_types
                          if attrs.get(item))
        if item_changed and num_defined != 1:
            message = ('A valid value for exactly one of the following '
                       'parameters must be defined: %s' % ','.join(
                        self.Meta.item_types))
            raise serializers.ValidationError(message)
        return attrs

    def get_item_type(self, obj):
        for item_type in self.Meta.item_types:
            if getattr(obj, item_type):
                return item_type
        return
