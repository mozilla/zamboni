from django.conf import settings
from django.db.models import Q
from django.db.transaction import non_atomic_requests
from django.utils.datastructures import MultiValueDictKeyError
from django.http import Http404
from django.views.decorators.cache import cache_control

import commonware
from django_statsd.clients import statsd
from elasticsearch_dsl import filter as es_filter
from elasticsearch_dsl import function as es_function
from elasticsearch_dsl import query, Search
from PIL import Image
from rest_framework import generics, response, status, viewsets
from rest_framework.exceptions import ParseError, PermissionDenied
from rest_framework.filters import BaseFilterBackend, OrderingFilter
from rest_framework.response import Response
from rest_framework.serializers import Serializer, ValidationError
from rest_framework.views import APIView

import mkt
import mkt.feed.constants as feed
from mkt.access import acl
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.api.paginator import ESPaginator
from mkt.constants.carriers import CARRIER_MAP
from mkt.constants.regions import REGIONS_DICT
from mkt.developers.tasks import pngcrush_image
from mkt.feed.indexers import FeedItemIndexer
from mkt.operators.models import OperatorPermission
from mkt.search.filters import (DeviceTypeFilter, ProfileFilter,
                                PublicAppsFilter, RegionFilter)
from mkt.site.storage_utils import public_storage
from mkt.site.utils import HttpResponseSendFile
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp

from .authorization import FeedAuthorization
from .fields import DataURLImageField, ImageURLField
from .models import FeedApp, FeedBrand, FeedCollection, FeedItem, FeedShelf
from .serializers import (FeedAppESSerializer, FeedAppSerializer,
                          FeedBrandESSerializer, FeedBrandSerializer,
                          FeedCollectionESSerializer, FeedCollectionSerializer,
                          FeedItemESSerializer, FeedItemSerializer,
                          FeedShelfESSerializer, FeedShelfSerializer)


log = commonware.log.getLogger('z.feed')


class ImageURLUploadMixin(viewsets.ModelViewSet):
    """
    Attaches pre/post save methods for image handling.

    The pre_save downloads an image from a URL and validates. The post_save
    saves the image in feed element's directory.

    We look at the class' `image_fields` property for the list of tuples to
    check. The tuples are the names of the the image form name, the hash field,
    and a suffix to append to the image file name::

        image_fields = ('background_image_upload_url', 'image_hash', '')

    """

    def pre_save(self, obj):
        """Download and validate image URL."""
        for image_field, hash_field, suffix in self.image_fields:
            if self.request.DATA.get(image_field):
                img, hash_ = ImageURLField().from_native(
                    self.request.DATA[image_field])
                # Store img for `post_save` where we have access to the pk so
                # we can save img in appropriate directory.
                setattr(obj, '_%s' % image_field, img)
                setattr(obj, hash_field, hash_)
            elif hasattr(obj, 'type') and obj.type == feed.COLLECTION_PROMO:
                # Remove background images for promo collections.
                setattr(obj, hash_field, None)

        return super(ImageURLUploadMixin, self).pre_save(obj)

    def post_save(self, obj, created=True):
        """Store image that we attached to the obj in pre_save."""
        for image_field, hash_field, suffix in self.image_fields:
            image = getattr(obj, '_%s' % image_field, None)
            if image:
                i = Image.open(image)
                path = obj.image_path(suffix)
                with public_storage.open(path, 'wb') as f:
                    i.save(f, 'png')
                pngcrush_image.delay(path, set_modified_on=[obj])

        return super(ImageURLUploadMixin, self).post_save(obj, created)


class GroupedAppsViewSetMixin(object):
    def set_apps_grouped(self, obj, apps):
        if apps:
            try:
                obj.set_apps_grouped(apps)
            except Webapp.DoesNotExist:
                raise ParseError(detail=self.exceptions['doesnt_exist'])

    def set_apps(self, obj, apps):
        """
        Attempt to set the apps via the superclass, catching and handling the
        TypeError raised if the apps are passed in a grouped manner.
        """
        try:
            super(GroupedAppsViewSetMixin, self).set_apps(obj, apps)
        except TypeError:
            self.set_apps_grouped(obj, apps)


class BaseFeedCollectionViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                                ImageURLUploadMixin):
    """
    Base viewset for subclasses of BaseFeedCollection.
    """
    serializer_class = None
    queryset = None
    cors_allowed_methods = ('get', 'post', 'delete', 'patch', 'put')
    permission_classes = [FeedAuthorization]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]

    exceptions = {
        'doesnt_exist': 'One or more of the specified `apps` do not exist.'
    }
    image_fields = (('background_image_upload_url', 'image_hash', ''),)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(
            self.filter_queryset(self.get_queryset()))
        serializer = self.get_pagination_serializer(page)
        return response.Response(serializer.data)

    def set_apps(self, obj, apps):
        if apps:
            try:
                obj.set_apps(apps)
            except Webapp.DoesNotExist:
                raise ParseError(detail=self.exceptions['doesnt_exist'])

    def create(self, request, *args, **kwargs):
        apps = request.DATA.pop('apps', [])
        serializer = self.get_serializer(data=request.DATA,
                                         files=request.FILES)
        if serializer.is_valid():
            self.pre_save(serializer.object)
            self.object = serializer.save(force_insert=True)
            self.set_apps(self.object, apps)
            self.post_save(self.object, created=True)
            headers = self.get_success_headers(serializer.data)
            return response.Response(serializer.data,
                                     status=status.HTTP_201_CREATED,
                                     headers=headers)
        return response.Response(serializer.errors,
                                 status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        apps = request.DATA.pop('apps', [])
        self.set_apps(self.get_object(), apps)
        ret = super(BaseFeedCollectionViewSet, self).update(
            request, *args, **kwargs)
        return ret


class RegionCarrierFilter(BaseFilterBackend):
    def filter_queryset(self, request, qs, view):
        q = request.QUERY_PARAMS

        # Filter for only the region if specified.
        if q.get('region') and q.get('region') in mkt.regions.REGIONS_DICT:
            region_id = mkt.regions.REGIONS_DICT[q['region']].id
            qs = qs.filter(region=region_id)

        # Exclude feed items that specify carrier but do not match carrier.
        if q.get('carrier') and q.get('carrier') in mkt.carriers.CARRIER_MAP:
            carrier = mkt.carriers.CARRIER_MAP[q['carrier']].id
            qs = qs.exclude(~Q(carrier=carrier), carrier__isnull=False)

        return qs


class FeedItemViewSet(CORSMixin, viewsets.ModelViewSet):
    """
    A viewset for the FeedItem class, which wraps all items that live on the
    feed.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter, RegionCarrierFilter)
    queryset = FeedItem.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put', 'patch')
    serializer_class = FeedItemSerializer


class FeedBuilderView(CORSMixin, APIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Feed', 'Curate')]
    cors_allowed_methods = ('put',)

    def put(self, request, *args, **kwargs):
        """
        For each region in the object:
        Deletes all of the (carrier-less) FeedItems in the region.
        Batch create all of the FeedItems in order for each region.

        -- feed - object of regions that point to a list of feed
                  element IDs (as well as their type) .
        {
            'us': [
                ['app', 36L],
                ['app', 42L],
                ['collection', 12L],
                ['brand', 12L]
            ]
        }
        """
        regions = [mkt.regions.REGIONS_DICT[region].id
                   for region in request.DATA.keys()]
        FeedItem.objects.filter(
            carrier=None, region__in=regions).delete()

        feed_items = []
        for region, feed_elements in request.DATA.items():
            for order, feed_element in enumerate(feed_elements):
                try:
                    item_type, item_id = feed_element
                except ValueError:
                    return response.Response(
                        'Expected two-element arrays.',
                        status=status.HTTP_400_BAD_REQUEST)
                feed_item = {
                    'region': mkt.regions.REGIONS_DICT[region].id,
                    'order': order,
                    'item_type': item_type,
                }
                feed_item[item_type + '_id'] = item_id
                feed_items.append(FeedItem(**feed_item))

        FeedItem.objects.bulk_create(feed_items)

        # Index the feed items created. bulk_create doesn't call save or
        # post_save so get the IDs manually.
        feed_item_ids = list(FeedItem.objects.filter(region__in=regions)
                             .values_list('id', flat=True))
        FeedItem.get_indexer().index_ids(feed_item_ids, no_delay=True)

        return response.Response(status=status.HTTP_201_CREATED)


class FeedAppViewSet(CORSMixin, MarketplaceView, SlugOrIdMixin,
                     ImageURLUploadMixin):
    """
    A viewset for the FeedApp class, which highlights a single app and some
    additional metadata (e.g. a review or a screenshot).
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    filter_backends = (OrderingFilter,)
    queryset = FeedApp.objects.all()
    cors_allowed_methods = ('get', 'delete', 'post', 'put', 'patch')
    serializer_class = FeedAppSerializer

    image_fields = (('background_image_upload_url', 'image_hash', ''),)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(
            self.filter_queryset(self.get_queryset()))
        serializer = self.get_pagination_serializer(page)
        return response.Response(serializer.data)


class FeedBrandViewSet(BaseFeedCollectionViewSet):
    """
    A viewset for the FeedBrand class, a type of collection that allows editors
    to quickly create content without involving localizers.
    """
    queryset = FeedBrand.objects.all()
    serializer_class = FeedBrandSerializer


class FeedCollectionViewSet(GroupedAppsViewSetMixin,
                            BaseFeedCollectionViewSet):
    """
    A viewset for the FeedCollection class.
    """
    queryset = FeedCollection.objects.all()
    serializer_class = FeedCollectionSerializer


class FeedShelfPermissionMixin(object):
    """
    There are some interesting permissions-related things going on with
    FeedShelves. DRF will never run object-level permissions checks (i.e.
    has_object_permission) if the user fails the top-level checks (i.e.
    has_permission), but there are cases with FeedShelf objects where access
    to an object requires access to properties of the object. This means we
    have to manually make these checks in the viewsets.

    This mixin provides all the necessary methods to do so.
    """

    def req_data(self):
        """
        Returns a MultiDict containing the request data. This is shimmed to
        ensure that it works if passed either rest_framework's Request class
        or Django's WSGIRequest class.
        """
        return (self.request.DATA if hasattr(self.request, 'DATA') else
                self.request.POST)

    def is_admin(self, user):
        """
        Returns a boolean indicating whether the passed user passes either
        OperatorDashboard:* or Feed:Curate.
        """
        return (acl.action_allowed(self.request, 'OperatorDashboard', '*') or
                acl.action_allowed(self.request, 'Feed', 'Curate'))

    def require_operator_permission(self, user, carrier, region):
        """
        Raises PermissionDenied if the passed user does not have an
        OperatorPermission object for the passed carrier and region.
        """
        if user.is_anonymous():
            raise PermissionDenied()
        elif self.is_admin(user):
            return
        carrier = (carrier if isinstance(carrier, (int, long)) else
                   CARRIER_MAP[carrier].id)
        region = (region if isinstance(region, (int, long)) else
                  REGIONS_DICT[region].id)
        passes = OperatorPermission.objects.filter(
            user=user, carrier=carrier, region=region).exists()
        if not passes:
            raise PermissionDenied()

    def require_object_permission(self, user, obj):
        """
        Raises PermissionDenied if the passed user does not have an
        OperatorPermission object for the passed Feedshelf object's carrier and
        region.
        """
        self.require_operator_permission(user, obj.carrier, obj.region)


class FeedShelfViewSet(GroupedAppsViewSetMixin, FeedShelfPermissionMixin,
                       BaseFeedCollectionViewSet):
    """
    A viewset for the FeedShelf class.
    """
    queryset = FeedShelf.objects.all()
    serializer_class = FeedShelfSerializer
    permission_classes = []

    image_fields = (
        ('background_image_upload_url', 'image_hash', ''),
        ('background_image_landing_upload_url', 'image_landing_hash',
         '_landing'),
    )

    def mine(self, request, *args, **kwargs):
        """
        Return all shelves a user can administer. Anonymous users will always
        receive an empty list.
        """
        qs = self.queryset
        if request.user.is_anonymous():
            qs = self.queryset.none()
        elif not self.is_admin(request.user):
            perms = OperatorPermission.objects.filter(user=request.user)
            if perms:
                query = Q()
                for perm in perms:
                    query |= Q(carrier=perm.carrier, region=perm.region)
                qs = self.queryset.filter(query)
            else:
                qs = self.queryset.none()
        self.object_list = self.filter_queryset(qs)
        serializer = self.get_serializer(self.object_list, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Raise PermissionDenied if the authenticating user does not pass the
        checks in require_operator_permission for the carrier and region in the
        request data.
        """
        data = self.req_data()
        try:
            self.require_operator_permission(
                request.user, data['carrier'], data['region'])
        except (KeyError, MultiValueDictKeyError):
            raise ParseError()
        return super(FeedShelfViewSet, self).create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        Raise PermissionDenied if the authenticating user does not pass the
        checks in require_operator_permission for the carrier and region on the
        FeedShelf object they are attempting to update.
        """
        self.require_object_permission(request.user, self.get_object())
        return super(FeedShelfViewSet, self).update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Raise PermissionDenied if the authenticating user does not pass the
        checks in require_operator_permission for the carrier and region on the
        FeedShelf object they are attempting to destroy.
        """
        self.require_object_permission(request.user, self.get_object())
        return super(FeedShelfViewSet, self).destroy(request, *args, **kwargs)


class FeedShelfPublishView(FeedShelfPermissionMixin, CORSMixin, APIView):
    """
    put -- creates a FeedItem for a FeedShelf with respective carrier/region
        pair.  Deletes any currently existing FeedItems with the carrier/region
        pair to effectively "unpublish" it since only one shelf can be toggled
        at a time for a carrier/region.

    delete -- deletes the FeedItem for a FeedShelf with respective
        carrier/region.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = []
    cors_allowed_methods = ('delete', 'put',)

    def get_object(self, pk):
        if pk.isdigit():
            obj = FeedShelf.objects.get(pk=pk)
        else:
            obj = FeedShelf.objects.get(slug=pk)
        self.require_object_permission(self.request.user, obj)
        return obj

    def put(self, request, *args, **kwargs):
        try:
            shelf = self.get_object(self.kwargs['pk'])
        except FeedShelf.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        feed_item_kwargs = {
            'item_type': feed.FEED_TYPE_SHELF,
            'carrier': shelf.carrier,
            'region': shelf.region
        }
        FeedItem.objects.filter(**feed_item_kwargs).delete()
        feed_item = FeedItem.objects.create(shelf_id=shelf.id,
                                            **feed_item_kwargs)

        # Return.
        serializer = FeedItemSerializer(feed_item, context={
            'request': self.request,
        })
        return response.Response(serializer.data,
                                 status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        try:
            shelf = self.get_object(self.kwargs['pk'])
        except FeedShelf.DoesNotExist:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        feed_item_kwargs = {
            'item_type': feed.FEED_TYPE_SHELF,
            'carrier': shelf.carrier,
            'region': shelf.region
        }
        FeedItem.objects.filter(**feed_item_kwargs).delete()

        # Return.
        return response.Response(status=status.HTTP_204_NO_CONTENT)


class CollectionImageViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                             generics.GenericAPIView, viewsets.ViewSet):
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('Feed', 'Curate'))]
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    cors_allowed_methods = ('get', 'put', 'delete')

    hash_field = 'image_hash'
    image_suffix = ''

    # Dummy serializer to keep DRF happy when it's answering to OPTIONS.
    serializer_class = Serializer

    def perform_content_negotiation(self, request, force=False):
        """
        Force DRF's content negociation to not raise an error - It wants to use
        the format passed to the URL, but we don't care since we only deal with
        "raw" content: we don't even use the renderers.
        """
        return super(CollectionImageViewSet, self).perform_content_negotiation(
            request, force=True)

    @cache_control(max_age=60 * 60 * 24 * 365)
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        if not getattr(obj, 'image_hash', None):
            raise Http404
        return HttpResponseSendFile(request, obj.image_path(self.image_suffix),
                                    content_type='image/png')

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        try:
            img, hash_ = DataURLImageField().from_native(request.read())
        except ValidationError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        i = Image.open(img)
        with public_storage.open(obj.image_path(self.image_suffix), 'wb') as f:
            i.save(f, 'png')
        # Store the hash of the original image data sent.
        obj.update(**{self.hash_field: hash_})

        pngcrush_image.delay(obj.image_path(self.image_suffix))
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if getattr(obj, 'image_hash', None):
            public_storage.delete(obj.image_path(self.image_suffix))
            obj.update(**{self.hash_field: None})
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()


class FeedCollectionImageViewSet(CollectionImageViewSet):
    queryset = FeedCollection.objects.all()


class FeedShelfImageViewSet(FeedShelfPermissionMixin, CollectionImageViewSet):
    queryset = FeedShelf.objects.all()


class FeedShelfLandingImageViewSet(FeedShelfPermissionMixin,
                                   CollectionImageViewSet):
    queryset = FeedShelf.objects.all()
    hash_field = 'image_landing_hash'
    image_suffix = '_landing'


class BaseFeedESView(CORSMixin, APIView):
    filter_backends = [PublicAppsFilter, DeviceTypeFilter, RegionFilter,
                       ProfileFilter]

    def __init__(self, *args, **kw):
        self.ITEM_TYPES = {
            'apps': feed.FEED_TYPE_APP,
            'brands': feed.FEED_TYPE_BRAND,
            'collections': feed.FEED_TYPE_COLL,
            'shelves': feed.FEED_TYPE_SHELF,
        }
        self.PLURAL_TYPES = dict((v, k) for k, v in self.ITEM_TYPES.items())
        self.SERIALIZERS = {
            feed.FEED_TYPE_APP: FeedAppESSerializer,
            feed.FEED_TYPE_BRAND: FeedBrandESSerializer,
            feed.FEED_TYPE_COLL: FeedCollectionESSerializer,
            feed.FEED_TYPE_SHELF: FeedShelfESSerializer,
        }
        self.INDICES = {
            feed.FEED_TYPE_APP: settings.ES_INDEXES['mkt_feed_app'],
            feed.FEED_TYPE_BRAND: settings.ES_INDEXES['mkt_feed_brand'],
            feed.FEED_TYPE_COLL: settings.ES_INDEXES['mkt_feed_collection'],
            feed.FEED_TYPE_SHELF: settings.ES_INDEXES['mkt_feed_shelf'],
        }
        super(BaseFeedESView, self).__init__(*args, **kw)

    def get_feed_element_index(self):
        """Return a list of index to query all at once."""
        return [
            settings.ES_INDEXES['mkt_feed_app'],
            settings.ES_INDEXES['mkt_feed_brand'],
            settings.ES_INDEXES['mkt_feed_collection'],
            settings.ES_INDEXES['mkt_feed_shelf']
        ]

    def get_app_ids(self, feed_element):
        """Get a single feed element's app IDs."""
        if hasattr(feed_element, 'app'):
            return [feed_element.app]
        return feed_element.apps

    def get_app_ids_all(self, feed_elements):
        """From a list of feed_elements, return a list of app IDs."""
        app_ids = []
        for elm in feed_elements:
            app_ids += self.get_app_ids(elm)
        return app_ids

    def get_apps(self, request, app_ids):
        """
        Takes a list of app_ids. Gets the apps, including filters.
        Returns an app_map for serializer context.
        """
        sq = WebappIndexer.search()
        if request.QUERY_PARAMS.get('filtering', '1') == '1':
            # With filtering (default).
            for backend in self.filter_backends:
                sq = backend().filter_queryset(request, sq, self)
        sq = WebappIndexer.filter_by_apps(app_ids, sq)

        # Store the apps to attach to feed elements later.
        with statsd.timer('mkt.feed.views.apps_query'):
            apps = sq.execute().hits
        return dict((app.id, app) for app in apps)

    def filter_feed_items(self, request, feed_items):
        """
        Removes feed items from the feed if they do not meet some
        requirements like app count.
        """
        for feed_item in feed_items:
            item_type = feed_item['item_type']
            feed_item[item_type] = self.filter_feed_element(
                request, feed_item[item_type], item_type)

        # Filter out feed elements that did not pass the filters.
        return filter(lambda item: item[item['item_type']], feed_items)

    def filter_feed_element(self, request, feed_element, item_type):
        """
        If a feed element does not have enough apps, return None.
        Else return the feed element.
        """
        if not feed_element:
            # Handle edge case where the ES index might get stale.
            return None

        if request.QUERY_PARAMS.get('filtering', '1') == '0':
            # Without filtering
            return feed_element

        # No empty collections.
        if 'app_count' in feed_element and feed_element['app_count'] == 0:
            return None

        # If the app of a featured app was filtered out.
        if item_type == feed.FEED_TYPE_APP and not feed_element['app']:
            return None

        # Enforce minimum apps on collections.
        if (item_type == feed.FEED_TYPE_COLL and
                feed_element['app_count'] < feed.MIN_APPS_COLLECTION):
            return None

        return feed_element

    @classmethod
    def as_view(cls, **kwargs):
        # Make all search views non_atomic: they should not need the db, or
        # at least they should not need to make db writes, so they don't need
        # to be wrapped in transactions.
        view = super(BaseFeedESView, cls).as_view(**kwargs)
        return non_atomic_requests(view)


class FeedElementSearchView(BaseFeedESView):
    """
    Search view for the Curation Tools.

    Returns an object keyed by feed element type
    ('apps', 'brands', 'collections').
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Feed', 'Curate')]
    cors_allowed_methods = ('get',)

    def _phrase(self, q):
        return {
            'query': q,
            'type': 'phrase',
            'slop': 2,
        }

    def get(self, request, *args, **kwargs):
        q = request.GET.get('q')

        # Make search.
        queries = [
            query.Q('match', slug=self._phrase(q)),  # Slug.
            query.Q('match', type=self._phrase(q)),  # Type.
            query.Q('match', search_names=self._phrase(q)),  # Name.
            query.Q('prefix', carrier=q),  # Shelf carrier.
            query.Q('term', region=q)  # Shelf region.
        ]
        sq = query.Bool(should=queries)

        # Search.
        res = {'apps': [], 'brands': [], 'collections': [], 'shelves': []}
        es = Search(using=FeedItemIndexer.get_es(),
                    index=self.get_feed_element_index())
        feed_elements = es.query(sq).execute().hits
        if not feed_elements:
            return response.Response(res, status=status.HTTP_404_NOT_FOUND)

        # Deserialize.
        ctx = {'app_map': self.get_apps(request,
                                        self.get_app_ids_all(feed_elements)),
               'request': request}
        for feed_element in feed_elements:
            item_type = feed_element.item_type
            serializer = self.SERIALIZERS[item_type]
            data = serializer(feed_element, context=ctx).data
            res[self.PLURAL_TYPES[item_type]].append(data)

        # Return.
        return response.Response(res, status=status.HTTP_200_OK)


class FeedView(MarketplaceView, BaseFeedESView, generics.GenericAPIView):
    """
    THE feed view. It hits ES with:
    - a weighted function score query to get feed items
    - a filter to deserialize feed elements
    - a filter to deserialize apps
    """
    authentication_classes = []
    cors_allowed_methods = ('get',)
    paginator_class = ESPaginator
    permission_classes = []

    def get_es_feed_query(self, sq, region=mkt.regions.RESTOFWORLD.id,
                          carrier=None, original_region=None):
        """
        Build ES query for feed.
        Must match region.
        Orders by FeedItem.order.
        Boosted operator shelf matching region + carrier.
        Boosted operator shelf matching original_region + carrier.

        region -- region ID (integer)
        carrier -- carrier ID (integer)
        original_region -- region from before we were falling back,
            to keep the original shelf atop the RoW feed.
        """
        region_filter = es_filter.Term(region=region)
        shelf_filter = es_filter.Term(item_type=feed.FEED_TYPE_SHELF)

        ordering_fn = es_function.FieldValueFactor(
            field='order', modifier='reciprocal',
            filter=es_filter.Bool(must=[region_filter],
                                  must_not=[shelf_filter]))
        boost_fn = es_function.BoostFactor(value=10000.0,
                                           filter=shelf_filter)

        if carrier is None:
            # If no carrier, just match the region and exclude shelves.
            return sq.query('function_score',
                            functions=[ordering_fn],
                            filter=es_filter.Bool(
                                must=[region_filter],
                                must_not=[shelf_filter]
                            ))

        # Must match region.
        # But also include the original region if we falling back to RoW.
        # The only original region feed item that will be included is a shelf
        # else we wouldn't be falling back in the first place.
        region_filters = [region_filter]
        if original_region:
            region_filters.append(es_filter.Term(region=original_region))

        return sq.query(
            'function_score',
            functions=[boost_fn, ordering_fn],
            filter=es_filter.Bool(
                should=region_filters,
                # Filter out shelves that don't match the carrier.
                must_not=[es_filter.Bool(
                    must=[shelf_filter],
                    must_not=[es_filter.Term(carrier=carrier)])])
        )

    def get_es_feed_element_query(self, sq, feed_items):
        """
        From a list of FeedItems with normalized feed element IDs,
        return an ES query that fetches the feed elements for each feed item.
        """
        filters = []
        for feed_item in feed_items:
            item_type = feed_item['item_type']
            filters.append(es_filter.Bool(
                must=[es_filter.Term(id=feed_item[item_type]),
                      es_filter.Term(item_type=item_type)]))

        return sq.filter(es_filter.Bool(should=filters))[0:len(feed_items)]

    def _check_empty_feed(self, items, rest_of_world):
        """
        Return -1 if feed is empty and we are already falling back to RoW.
        Return 0 if feed is empty and we are not falling back to RoW yet.
        Return 1 if at least one feed item and the only feed item is not shelf.
        """
        if not items or (len(items) == 1 and items[0].get('shelf')):
            # Empty feed.
            if rest_of_world:
                return -1
            return 0
        return 1

    def _handle_empty_feed(self, empty_feed_code, region, request, args,
                           kwargs):
        """
        If feed is empty, this method handles appropriately what to return.
        If empty_feed_code == 0: try to fallback to RoW.
        If empty_feed_code == -1: 404.
        """
        if empty_feed_code == 0:
            return self._get(request, rest_of_world=True,
                             original_region=region, *args, **kwargs)
        return response.Response(status=status.HTTP_404_NOT_FOUND)

    def _get(self, request, rest_of_world=False, original_region=None,
             *args, **kwargs):
        es = FeedItemIndexer.get_es()

        # Parse region.
        if rest_of_world:
            region = mkt.regions.RESTOFWORLD.id
        else:
            region = request.REGION.id
        # Parse carrier.
        carrier = None
        q = request.QUERY_PARAMS
        if q.get('carrier') and q['carrier'] in mkt.carriers.CARRIER_MAP:
            carrier = mkt.carriers.CARRIER_MAP[q['carrier']].id

        # Fetch FeedItems.
        sq = self.get_es_feed_query(FeedItemIndexer.search(using=es),
                                    region=region, carrier=carrier,
                                    original_region=original_region)
        # The paginator triggers the ES request.
        with statsd.timer('mkt.feed.view.feed_query'):
            feed_items = self.paginate_queryset(sq)
        feed_ok = self._check_empty_feed(feed_items, rest_of_world)
        if feed_ok != 1:
            return self._handle_empty_feed(feed_ok, region, request, args,
                                           kwargs)

        # Build the meta object.
        meta = mkt.api.paginator.CustomPaginationSerializer(
            feed_items, context={'request': request}).data['meta']

        # Set up serializer context.
        feed_element_map = {
            feed.FEED_TYPE_APP: {},
            feed.FEED_TYPE_BRAND: {},
            feed.FEED_TYPE_COLL: {},
            feed.FEED_TYPE_SHELF: {},
        }

        # Fetch feed elements to attach to FeedItems later.
        apps = []
        sq = self.get_es_feed_element_query(
            Search(using=es, index=self.get_feed_element_index()), feed_items)
        with statsd.timer('mkt.feed.view.feed_element_query'):
            feed_elements = sq.execute().hits
        for feed_elm in feed_elements:
            # Store the feed elements to attach to FeedItems later.
            feed_element_map[feed_elm['item_type']][feed_elm['id']] = feed_elm
            # Store the apps to retrieve later.
            apps += self.get_app_ids(feed_elm)

        # Remove dupes from apps list.
        apps = list(set(apps))

        # Fetch apps to attach to feed elements later.
        app_map = self.get_apps(request, apps)

        # Super serialize.
        with statsd.timer('mkt.feed.view.serialize'):
            feed_items = FeedItemESSerializer(feed_items, many=True, context={
                'app_map': app_map,
                'feed_element_map': feed_element_map,
                'request': request
            }).data

        # Filter excluded apps. If there are feed items that have all their
        # apps excluded, they will be removed from the feed.
        feed_items = self.filter_feed_items(request, feed_items)
        feed_ok = self._check_empty_feed(feed_items, rest_of_world)
        if feed_ok != 1:
            if not rest_of_world:
                log.warning('Feed empty for region {0}. Requerying feed with '
                            'region=RESTOFWORLD'.format(region))
            return self._handle_empty_feed(feed_ok, region, request, args,
                                           kwargs)

        return response.Response({'meta': meta, 'objects': feed_items},
                                 status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        with statsd.timer('mkt.feed.view'):
            return self._get(request, *args, **kwargs)


class FeedElementGetView(BaseFeedESView):
    """
    Fetches individual feed elements from ES. Detail views.
    """
    authentication_classes = []
    permission_classes = []
    cors_allowed_methods = ('get',)

    def get_feed_element_filter(self, sq, item_type, slug):
        """Matches a single feed element."""
        bool_filter = es_filter.Bool(must=[
            es_filter.Term(item_type=item_type),
            es_filter.Term(**{'slug.raw': slug})
        ])
        return sq.filter(bool_filter)

    def get(self, request, item_type, slug, **kwargs):
        item_type = self.ITEM_TYPES[item_type]

        # Hit ES.
        sq = self.get_feed_element_filter(
            Search(using=FeedItemIndexer.get_es(),
                   index=self.INDICES[item_type]),
            item_type, slug)
        try:
            feed_element = sq.execute().hits[0]
        except IndexError:
            return response.Response(status=status.HTTP_404_NOT_FOUND)

        # Deserialize.
        data = self.SERIALIZERS[item_type](feed_element, context={
            'app_map': self.get_apps(request, self.get_app_ids(feed_element)),
            'request': request
        }).data

        return response.Response(data, status=status.HTTP_200_OK)


class FeedElementListView(BaseFeedESView, MarketplaceView,
                          generics.GenericAPIView):
    """
    Fetches the five most recent of a feed element type for Curation Tools.
    With pagination.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Feed', 'Curate')]
    cors_allowed_methods = ('get',)
    paginator_class = ESPaginator

    def get_recent_feed_elements(self, sq):
        """Matches all sorted by recent."""
        return sq.sort('-created').query(query.MatchAll())

    def get(self, request, item_type, **kwargs):
        item_type = self.ITEM_TYPES[item_type]

        # Hit ES.
        sq = self.get_recent_feed_elements(
            Search(using=FeedItemIndexer.get_es(),
                   index=self.INDICES[item_type]))
        feed_elements = self.paginate_queryset(sq)
        if not feed_elements:
            return response.Response({'objects': []},
                                     status=status.HTTP_404_NOT_FOUND)

        # Deserialize. Manually use pagination serializer because this view
        # uses multiple serializers.
        meta = mkt.api.paginator.CustomPaginationSerializer(
            feed_elements, context={'request': request}).data['meta']
        objects = self.SERIALIZERS[item_type](feed_elements, context={
            'app_map': self.get_apps(request,
                                     self.get_app_ids_all(feed_elements)),
            'request': request
        }, many=True).data

        return response.Response({'meta': meta, 'objects': objects},
                                 status=status.HTTP_200_OK)
