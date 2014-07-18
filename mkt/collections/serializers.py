# -*- coding: utf-8 -*-
import hashlib
import os
import uuid

from rest_framework import serializers
from rest_framework.fields import get_component
from rest_framework.reverse import reverse
from tower import ugettext_lazy as _

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import default_storage as storage

import amo
import mkt
from mkt.api.fields import (SlugChoiceField, TranslationSerializerField,
                            UnicodeChoiceField)
from mkt.constants.categories import CATEGORY_CHOICES
from mkt.features.utils import get_feature_profile
from mkt.webapps.models import Webapp
from mkt.webapps.serializers import SimpleAppSerializer, SimpleESAppSerializer
from mkt.users.models import UserProfile

from .models import Collection
from .constants import COLLECTIONS_TYPE_FEATURED, COLLECTIONS_TYPE_OPERATOR


class CollectionMembershipField(serializers.RelatedField):
    """
    RelatedField subclass that serializes apps in a Collection, taking into
    account feature profile and optionally relying on ElasticSearch to find
    the apps instead of making a DB query.

    Specifically created for use with CollectionSerializer; you probably don't
    want to use this elsewhere.
    """
    app_serializer_classes = {
        'es': SimpleESAppSerializer,
        'normal': SimpleAppSerializer,
    }

    def to_native(self, qs, use_es=False):
        if use_es:
            serializer_class = self.app_serializer_classes['es']
        else:
            serializer_class = self.app_serializer_classes['normal']
        # To work around elasticsearch default limit of 10, hardcode a higher
        # limit.
        return serializer_class(qs[:100], context=self.context, many=True).data

    def _get_device(self, request):
        # Fireplace sends `dev` and `device`. See the API docs. When
        # `dev` is 'android' we also need to check `device` to pick a device
        # object.
        dev = request.GET.get('dev')
        device = request.GET.get('device')

        if dev == 'android' and device:
            dev = '%s-%s' % (dev, device)

        return amo.DEVICE_LOOKUP.get(dev)

    def field_to_native(self, obj, field_name):
        if not hasattr(self, 'context') or not 'request' in self.context:
            raise ImproperlyConfigured('Pass request in self.context when'
                                       ' using CollectionMembershipField.')

        request = self.context['request']

        # Having 'use-es-for-apps' in the context means the parent view wants
        # us to use ES to fetch the apps. If that key is present, check that we
        # have a view in the context and that the waffle flag is active. If
        # everything checks out, bypass the db and use ES to fetch apps for a
        # nice performance boost.
        if self.context.get('use-es-for-apps') and self.context.get('view'):
            return self.field_to_native_es(obj, request)

        qs = get_component(obj, self.source)

        # Filter apps based on device and feature profiles.
        device = self._get_device(request)
        profile = get_feature_profile(request)
        if device and device != amo.DEVICE_DESKTOP:
            qs = qs.filter(addondevicetype__device_type=device.id)
        if profile:
            qs = qs.filter(**profile.to_kwargs(
                prefix='_current_version__features__has_'))

        return self.to_native(qs)

    def field_to_native_es(self, obj, request):
        """
        A version of field_to_native that uses ElasticSearch to fetch the apps
        belonging to the collection instead of SQL.

        Relies on a FeaturedSearchView instance in self.context['view']
        to properly rehydrate results returned by ES.
        """
        profile = get_feature_profile(request)
        region = self.context['view'].get_region_from_request(request)
        device = self._get_device(request)

        _rget = lambda d: getattr(request, d, False)
        qs = Webapp.from_search(request, region=region, gaia=_rget('GAIA'),
                                mobile=_rget('MOBILE'), tablet=_rget('TABLET'))
        filters = {'collection.id': obj.pk}
        if device and device != amo.DEVICE_DESKTOP:
            filters['device'] = device.id
        if profile:
            filters.update(**profile.to_kwargs(prefix='features.has_'))
        qs = qs.filter(**filters).order_by({
            'collection.order': {
                'order': 'asc',
                'nested_filter': {
                    'term': {'collection.id': obj.pk}
                }
            }
        })

        return self.to_native(qs, use_es=True)


class CollectionImageField(serializers.HyperlinkedRelatedField):
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


class CollectionSerializer(serializers.ModelSerializer):
    name = TranslationSerializerField(min_length=1)
    description = TranslationSerializerField()
    slug = serializers.CharField(required=False)
    collection_type = serializers.IntegerField()
    apps = CollectionMembershipField(many=True, source='apps')
    image = CollectionImageField(
        source='*',
        view_name='collection-image-detail',
        format='png')
    carrier = SlugChoiceField(required=False, empty=None,
        choices_dict=mkt.carriers.CARRIER_MAP)
    region = SlugChoiceField(required=False, empty=None,
        choices_dict=mkt.regions.REGION_LOOKUP)
    category = UnicodeChoiceField(required=False, empty=None,
        choices=CATEGORY_CHOICES)

    class Meta:
        fields = ('apps', 'author', 'background_color', 'can_be_hero',
                  'carrier', 'category', 'collection_type', 'default_language',
                  'description', 'id', 'image', 'is_public', 'name', 'region',
                  'slug', 'text_color',)
        model = Collection

    def to_native(self, obj):
        """
        Remove `can_be_hero` from the serialization if this is not an operator
        shelf.
        """
        native = super(CollectionSerializer, self).to_native(obj)
        if native['collection_type'] != COLLECTIONS_TYPE_OPERATOR:
            del native['can_be_hero']
        return native

    def validate(self, attrs):
        """
        Prevent operator shelves from being associated with a category.
        """
        existing = getattr(self, 'object')
        exc = 'Operator shelves may not be associated with a category.'

        if (not existing and attrs['collection_type'] ==
            COLLECTIONS_TYPE_OPERATOR and attrs.get('category')):
            raise serializers.ValidationError(exc)

        elif existing:
            collection_type = attrs.get('collection_type',
                                        existing.collection_type)
            category = attrs.get('category', existing.category)
            if collection_type == COLLECTIONS_TYPE_OPERATOR and category:
                raise serializers.ValidationError(exc)

        return attrs

    def full_clean(self, instance):
        instance = super(CollectionSerializer, self).full_clean(instance)
        if not instance:
            return None
        # For featured apps and operator shelf collections, we need to check if
        # one already exists for the same region/category/carrier combination.
        #
        # Sadly, this can't be expressed as a db-level unique constraint,
        # because this doesn't apply to basic collections.
        #
        # We have to do it ourselves, and we need the rest of the validation
        # to have already taken place, and have the incoming data and original
        # data from existing instance if it's an edit, so full_clean() is the
        # best place to do it.
        unique_collections_types = (COLLECTIONS_TYPE_FEATURED,
                                    COLLECTIONS_TYPE_OPERATOR)
        qs = Collection.objects.filter(
            collection_type=instance.collection_type,
            category=instance.category,
            region=instance.region,
            carrier=instance.carrier)
        if instance.pk:
            qs = qs.exclude(pk=instance.pk)
        if (instance.collection_type in unique_collections_types and
            qs.exists()):
            self._errors['collection_uniqueness'] = _(
                u'You can not have more than one Featured Apps/Operator Shelf '
                u'collection for the same category/carrier/region combination.'
            )
        return instance


class CuratorSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ('display_name', 'email', 'id')
        model = UserProfile


class DataURLImageField(serializers.CharField):
    def from_native(self, data):
        if data.startswith('"') and data.endswith('"'):
            # Strip quotes if necessary.
            data = data[1:-1]
        if not data.startswith('data:'):
            raise serializers.ValidationError('Not a data URI.')

        metadata, encoded = data.rsplit(',', 1)
        parts = metadata.rsplit(';', 1)
        if parts[-1] == 'base64':
            content = encoded.decode('base64')
            tmp_dst = os.path.join(settings.TMP_PATH, 'icon', uuid.uuid4().hex)
            with storage.open(tmp_dst, 'wb') as f:
                f.write(content)
            tmp = File(storage.open(tmp_dst))
            hash_ = hashlib.md5(content).hexdigest()[:8]
            return serializers.ImageField().from_native(tmp), hash_
        else:
            raise serializers.ValidationError('Not a base64 data URI.')

    def to_native(self, value):
        return value.name
