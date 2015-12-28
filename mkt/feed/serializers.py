from django.conf import settings
from django.utils.text import slugify

from mpconstants import collection_colors
from rest_framework import relations, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.reverse import reverse

import mkt.carriers
import mkt.feed.constants as feed
import mkt.regions
from mkt.api.fields import (ESTranslationSerializerField, SlugChoiceField,
                            SplitField, TranslationSerializerField,
                            UnicodeChoiceField)
from mkt.api.serializers import URLSerializerMixin
from mkt.carriers import CARRIER_CHOICE_DICT
from mkt.constants.categories import CATEGORY_CHOICES
from mkt.regions import REGIONS_CHOICES_ID_DICT
from mkt.search.serializers import BaseESSerializer
from mkt.submit.serializers import FeedPreviewESSerializer
from mkt.webapps.models import Preview, Webapp
from mkt.webapps.serializers import AppSerializer

from . import constants
from .fields import (AppESField, AppESHomeField, AppESHomePromoCollectionField,
                     FeedCollectionMembershipField)
from .models import (FeedApp, FeedBrand, FeedCollection,
                     FeedCollectionMembership, FeedItem, FeedShelf,
                     FeedShelfMembership)


class ValidateSlugMixin(object):
    """
    Rather than raise validation errors on slugs, coerce them into something
    safer.
    """

    def validate_slug(self, value):
        return slugify(unicode(value))


class BaseFeedCollectionSerializer(ValidateSlugMixin, URLSerializerMixin,
                                   serializers.ModelSerializer):
    """
    Base serializer for subclasses of BaseFeedCollection.
    """
    apps = FeedCollectionMembershipField(many=True, queryset=Webapp.objects,
                                         required=False)
    slug = serializers.CharField(required=False)

    # Search-specific.
    app_count = serializers.SerializerMethodField()
    preview_icon = serializers.SerializerMethodField()

    def get_app_count(self, obj):
        return obj.apps().count()

    def get_preview_icon(self, obj):
        if obj.apps().exists():
            return obj.apps()[0].get_icon_url(48)

    class Meta:
        fields = ('apps', 'slug', 'url')


class BaseFeedCollectionESSerializer(BaseESSerializer):
    """
    Base serializer for subclasses of BaseFeedCollection that serializes ES
    representation.
    """
    apps = AppESField(source='_app_ids', many=True)
    app_count = serializers.SerializerMethodField()

    def get_apps(self, obj):
        """
        Manually deserialize the app field, used to get the app count.
        The reason we don't just do len(obj._app_ids) is because ES may have
        filtered out some apps. These apps won't exist in the app map, so it
        will affect our total app count. This forces us to run the to_native
        operation twice, but it is not expensive.
        """
        app_field = AppESHomeField(many=True)
        app_field.context = self.context
        return app_field.to_representation(obj._app_ids)

    def get_app_count(self, obj):
        return len(self.get_apps(obj))


class FeedImageField(serializers.Field):
    hash_field = 'image_hash'
    view_name = 'api-v2:feed-app-image-detail'

    def get_value(self, data):
        return data.get(self.field_name + '_upload_url')

    def to_internal_value(self, data):
        return data

    def get_attribute(self, obj):
        return (getattr(obj, self.hash_field), obj.pk)

    def to_representation(self, (hash_, pk)):
        if hash_:
            # Always prefix with STATIC_URL to return images from our CDN.
            prefix = settings.STATIC_URL.strip('/')
            request = self.context.get('request', None)
            url = reverse(self.view_name, kwargs={'pk': pk},
                          request=request, format='png')
            # Always append image_hash so that we can send far-future expires.
            return '%s%s?%s' % (prefix, url, hash_)
        else:
            return None


class FeedLandingImageField(FeedImageField):
    view_name = 'api-v2:feed-shelf-landing-image-detail'
    hash_field = 'image_landing_hash'


class FeedAppSerializer(ValidateSlugMixin, URLSerializerMixin,
                        serializers.ModelSerializer):
    """
     A serializer for the FeedApp class, which highlights a single app and some
    additional metadata (e.g. a review or a screenshot).
    """
    app = SplitField(relations.PrimaryKeyRelatedField(required=True,
                                                      queryset=Webapp.objects),
                     AppSerializer())
    background_image = FeedImageField(allow_null=True)
    description = TranslationSerializerField(required=False)
    preview = SplitField(
        relations.PrimaryKeyRelatedField(required=False,
                                         queryset=Preview.objects),
        FeedPreviewESSerializer())
    pullquote_rating = serializers.IntegerField(required=False, max_value=5,
                                                min_value=1)
    pullquote_text = TranslationSerializerField(required=False)

    class Meta:
        fields = ('app', 'background_color', 'background_image', 'color',
                  'created', 'description', 'id', 'preview',
                  'pullquote_attribution', 'pullquote_rating',
                  'pullquote_text', 'slug', 'type', 'url')
        model = FeedApp
        url_basename = 'feedapps'

    def validate(self, attrs):
        """
        Require `pullquote_text` if `pullquote_rating` or
        `pullquote_attribution` are set.
        """
        if (not attrs.get('pullquote_text') and
            (attrs.get('pullquote_rating') or
             attrs.get('pullquote_attribution'))):
            raise ValidationError('Pullquote text required if rating or '
                                  'attribution is defined.')
        return attrs


class FeedAppESSerializer(FeedAppSerializer, BaseESSerializer):
    """
    A serializer for the FeedApp class that serializes ES representation.
    """
    app = AppESField(source='_app_id')
    background_image = FeedImageField(allow_null=True)
    description = ESTranslationSerializerField(required=False)
    preview = FeedPreviewESSerializer(source='_preview')
    pullquote_text = ESTranslationSerializerField(required=False)

    def fake_object(self, data):
        feed_app = self._attach_fields(FeedApp(), data, (
            'id', 'background_color', 'color', 'image_hash',
            'pullquote_attribution', 'pullquote_rating', 'slug', 'type'
        ))
        feed_app._preview = data.get('preview')
        feed_app = self._attach_translations(feed_app, data, (
            'description', 'pullquote_text'
        ))

        feed_app._app_id = data.get('app')
        return feed_app


class FeedAppESHomeSerializer(FeedAppESSerializer):
    """Stripped down FeedAppESSerializer targeted for the homepage."""
    app = AppESHomeField(source='_app_id')


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
        fields = ('app_count', 'apps', 'id', 'layout', 'slug', 'type', 'url')
        model = FeedBrand
        url_basename = 'feedbrands'


class FeedBrandESSerializer(BaseFeedCollectionESSerializer,
                            FeedBrandSerializer):
    """
    A serializer for the FeedBrand class for ES representation.
    """
    apps = AppESField(source='_app_ids', many=True)

    def fake_object(self, data):
        brand = self._attach_fields(FeedBrand(), data, (
            'id', 'layout', 'slug', 'type'
        ))
        brand._app_ids = data.get('apps')
        return brand


class FeedBrandESHomeSerializer(FeedBrandESSerializer):
    """
    Stripped down FeedBrandESSerializer targeted for the homepage.
    Different from the other Feed*ESHomeSerializers because it uses its own
    app field.
    """
    apps = AppESHomeField(source='_app_ids', many=True,
                          limit=feed.HOME_NUM_APPS_BRAND)


class FeedCollectionSerializer(BaseFeedCollectionSerializer):
    """
    A serializer for the FeedCollection class.
    """
    type = serializers.ChoiceField(choices=constants.COLLECTION_TYPE_CHOICES)
    background_image = FeedImageField(allow_null=True)
    color = serializers.CharField(max_length=20, required=False)
    description = TranslationSerializerField(required=False)
    name = TranslationSerializerField()
    apps = serializers.SerializerMethodField()

    # Deprecated.
    background_color = serializers.CharField(max_length=7, required=False)

    class Meta:
        fields = ('app_count', 'apps', 'background_color', 'background_image',
                  'color', 'description', 'id', 'name', 'slug', 'type', 'url')
        model = FeedCollection
        url_basename = 'feedcollections'

    def validate_color(self, color):
        if (self.initial_data.get('type') == constants.COLLECTION_PROMO and
                not color):
            raise serializers.ValidationError(
                '`color` is required for `promo` collections.'
            )
        if color and color not in dict(collection_colors.COLLECTION_COLORS):
            raise serializers.ValidationError(
                '`Not a valid value for `color`.'
            )
        return color

    def get_apps(self, obj):
        """
        Return a list of serialized apps, adding each app's `group` to the
        serialization.
        """
        ret = []
        memberships = FeedCollectionMembership.objects.filter(obj_id=obj.id)
        field = TranslationSerializerField()
        field.bind('group', self)
        field.context = self.context
        for member in memberships:
            data = AppSerializer(member.app, context=self.context).data
            data['group'] = field.to_representation(
                field.get_attribute(member))
            ret.append(data)
        return ret


class FeedCollectionESSerializer(BaseFeedCollectionESSerializer,
                                 FeedCollectionSerializer):
    """
    A serializer for the FeedCollection class for ES representation.
    """
    apps = AppESField(source='_app_ids', many=True)
    description = ESTranslationSerializerField(required=False)
    name = ESTranslationSerializerField(required=False)

    def fake_object(self, data):
        collection = self._attach_fields(FeedCollection(), data, (
            'id', 'background_color', 'color', 'image_hash', 'slug', 'type'
        ))
        collection = self._attach_translations(collection, data, (
            'name', 'description'
        ))

        collection._app_ids = data.get('apps')

        # Attach groups.
        self.context['group_apps'] = data.get('group_apps')
        self.context['group_names'] = data.get('group_names')

        return collection


class FeedCollectionESHomeSerializer(FeedCollectionESSerializer):
    """Stripped down FeedCollectionESSerializer targeted for the homepage."""
    apps = serializers.SerializerMethodField()

    def get_apps(self, obj):
        if obj.type == feed.COLLECTION_PROMO:
            # Need app icons if not background image.
            app_field = AppESHomePromoCollectionField(
                many=True, limit=feed.HOME_NUM_APPS_PROMO_COLL)

        elif obj.type == feed.COLLECTION_LISTING:
            # Needs minimal app serialization like FeedBrand.
            app_field = AppESHomeField(many=True,
                                       limit=feed.HOME_NUM_APPS_LISTING_COLL)

        app_field.context = self.context
        return app_field.to_representation(obj._app_ids)


class FeedShelfSerializer(BaseFeedCollectionSerializer):
    """
    A serializer for the FeedBrand class, a type of collection that allows
    editors to quickly create content without involving localizers.
    """
    apps = serializers.SerializerMethodField()
    background_image = FeedImageField(allow_null=True)
    background_image_landing = FeedLandingImageField(allow_null=True)
    carrier = SlugChoiceField(choices_dict=mkt.carriers.CARRIER_MAP)
    description = TranslationSerializerField(required=False)
    is_published = serializers.BooleanField(required=False)
    name = TranslationSerializerField()
    region = SlugChoiceField(choices_dict=mkt.regions.REGION_LOOKUP)

    class Meta:
        fields = ['app_count', 'apps', 'background_image',
                  'background_image_landing', 'carrier', 'description', 'id',
                  'is_published', 'name', 'region', 'slug', 'url']
        model = FeedShelf
        url_basename = 'feedshelves'

    def get_apps(self, obj):
        """
        Return a list of serialized apps, adding each app's `group` to the
        serialization.
        """
        ret = []
        memberships = FeedShelfMembership.objects.filter(obj_id=obj.id)
        field = TranslationSerializerField()
        field.bind('group', self)
        field.context = self.context
        for member in memberships:
            data = AppSerializer(member.app, context=self.context).data
            data['group'] = field.to_representation(
                field.get_attribute(member))
            ret.append(data)
        return ret


class FeedShelfESSerializer(BaseFeedCollectionESSerializer,
                            FeedShelfSerializer):
    """A serializer for the FeedShelf class for ES representation."""
    apps = AppESField(source='_app_ids', many=True)
    description = ESTranslationSerializerField(required=False)
    name = ESTranslationSerializerField(required=False)

    class Meta(FeedShelfSerializer.Meta):
        fields = filter(lambda field: field != 'is_published',
                        FeedShelfSerializer.Meta.fields)

    def fake_object(self, data):
        shelf = self._attach_fields(FeedShelf(), data, (
            'id', 'carrier', 'image_hash', 'image_landing_hash', 'region',
            'slug'
        ))
        shelf = self._attach_translations(shelf, data, (
            'description', 'name'
        ))

        shelf._app_ids = data.get('apps')

        # Attach groups.
        self.context['group_apps'] = data.get('group_apps')
        self.context['group_names'] = data.get('group_names')

        return shelf


class FeedShelfESHomeSerializer(FeedShelfESSerializer):
    """Stripped down FeedShelfESSerializer targeted for the homepage."""
    apps = AppESHomePromoCollectionField(source='_app_ids', many=True,
                                         limit=feed.HOME_NUM_APPS_SHELF)


class FeedItemSerializer(URLSerializerMixin, serializers.ModelSerializer):
    """
    A serializer for the FeedItem class, which wraps all items that live on the
    feed.
    """
    carrier = SlugChoiceField(required=False,
                              choices_dict=mkt.carriers.CARRIER_MAP)
    region = SlugChoiceField(required=False,
                             choices_dict=mkt.regions.REGION_LOOKUP)
    category = UnicodeChoiceField(required=False, choices=CATEGORY_CHOICES)
    item_type = serializers.SerializerMethodField()

    # Types of objects that are allowed to be a feed item.
    app = SplitField(
        relations.PrimaryKeyRelatedField(
            required=False,
            queryset=FeedApp.objects),
        FeedAppSerializer())
    brand = SplitField(
        relations.PrimaryKeyRelatedField(required=False,
                                         queryset=FeedBrand.objects),
        FeedBrandSerializer())
    collection = SplitField(
        relations.PrimaryKeyRelatedField(required=False,
                                         queryset=FeedCollection.objects),
        FeedCollectionSerializer())
    shelf = SplitField(
        relations.PrimaryKeyRelatedField(required=False,
                                         queryset=FeedShelf.objects),
        FeedShelfSerializer())

    class Meta:
        fields = ('app', 'brand', 'carrier', 'category', 'collection', 'id',
                  'item_type', 'region', 'shelf', 'url')
        item_types = ('app', 'brand', 'collection', 'shelf',)
        model = FeedItem
        url_basename = 'feeditems'

    def validate(self, attrs):
        """
        Ensure that at least one object type is specified.
        """
        if len(attrs) == 0:
            raise serializers.ValidationError('Feed item cannot be empty.')
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

    def validate_shelf(self, shelf_id):
        """
        If `shelf` is defined, validate that the FeedItem's `carrier` and
        `region` match the `carrier` and `region on `shelf`.
        """
        if shelf_id:
            shelf = FeedShelf.objects.get(pk=shelf_id)

            carrier = CARRIER_CHOICE_DICT[shelf.carrier]
            if self.initial_data.get('carrier') != carrier.slug:
                raise serializers.ValidationError(
                    'Feed item carrier does not match operator shelf carrier.')

            region = REGIONS_CHOICES_ID_DICT[shelf.region]
            if self.initial_data.get('region') != region.slug:
                raise serializers.ValidationError(
                    'Feed item region does not match operator shelf region.')
        return shelf_id


class FeedItemESSerializer(FeedItemSerializer, BaseESSerializer):
    """
    A serializer for the FeedItem class from an ES object, which wraps all
    items that live on the feed.

    It will turn something like

    >> {'item_type': 'app', 'carrier': 1, 'region': 1, 'app': 140L, 'id': 229L}

    into a fully serialized FeedItem.

    self.context['app_map'] -- mapping of app IDs to ES app objects.
    self.context['feed_element_map'] -- mapping of feed element IDs to ES feed
                                        element objects.
    self.context['request'] -- Django request, mainly for translations.
    """
    app = FeedAppESHomeSerializer(required=False, source='_app')
    brand = FeedBrandESHomeSerializer(required=False, source='_brand')
    collection = FeedCollectionESHomeSerializer(required=False,
                                                source='_collection')
    shelf = FeedShelfESHomeSerializer(required=False, source='_shelf')
    item_type = serializers.CharField()

    def fake_object(self, data):
        feed_item = self._attach_fields(FeedItem(), data, (
            'id', 'carrier', 'category', 'item_type', 'region',
        ))

        # Already fetched the feed element from ES. Set it to deserialize.
        for item_type in self.Meta.item_types:
            setattr(
                feed_item, '_%s' % item_type,
                self.context['feed_element_map'][item_type].get(data.get(
                    item_type)))

        return feed_item
