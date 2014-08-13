from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.db.models import Q

from django_statsd.clients import statsd
from elasticsearch_dsl import filter as es_filter
from elasticsearch_dsl import function as es_function
from elasticsearch_dsl import query, Search
from PIL import Image
from rest_framework import generics, response, status, viewsets
from rest_framework.exceptions import ParseError
from rest_framework.filters import BaseFilterBackend, OrderingFilter
from rest_framework.views import APIView

import mkt
import mkt.feed.constants as feed
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.api.paginator import ESPaginator
from mkt.collections.views import CollectionImageViewSet
from mkt.developers.tasks import pngcrush_image
from mkt.feed.indexers import FeedItemIndexer
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp

from .authorization import FeedAuthorization
from .fields import ImageURLField
from .models import FeedApp, FeedBrand, FeedCollection, FeedItem, FeedShelf
from .serializers import (FeedAppESSerializer, FeedAppSerializer,
                          FeedBrandESSerializer, FeedBrandSerializer,
                          FeedCollectionESSerializer, FeedCollectionSerializer,
                          FeedItemESSerializer, FeedItemSerializer,
                          FeedShelfESSerializer, FeedShelfSerializer)


class ImageURLUploadMixin(viewsets.ModelViewSet):
    """
    Attaches a pre_save that downloads an image from a URL and validates.
    Attaches a post_save that saves the image in feed element's directory.
    """
    def pre_save(self, obj):
        """Download and validate background image upload URL."""
        if self.request.DATA.get('background_image_upload_url'):
            img, hash_ = ImageURLField().from_native(
                self.request.DATA['background_image_upload_url'])
            # Store img for post_save where we have access to the pk so we can
            # save img in appropriate directory.
            obj._background_image_upload = img
            obj.image_hash = hash_
        return super(ImageURLUploadMixin, self).pre_save(obj)

    def post_save(self, obj, created=True):
        """Store background image that we attached to the obj in pre_save."""
        if hasattr(obj, '_background_image_upload'):
            i = Image.open(obj._background_image_upload)
            with storage.open(obj.image_path(), 'wb') as f:
                i.save(f, 'png')
            pngcrush_image.delay(obj.image_path(), set_modified_on=[obj])

        return super(ImageURLUploadMixin, self).post_save(obj, created)


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
    queryset = FeedItem.objects.no_cache().all()
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


class FeedCollectionViewSet(BaseFeedCollectionViewSet):
    """
    A viewset for the FeedCollection class.
    """
    queryset = FeedCollection.objects.all()
    serializer_class = FeedCollectionSerializer

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
            super(FeedCollectionViewSet, self).set_apps(obj, apps)
        except TypeError:
            self.set_apps_grouped(obj, apps)


class FeedShelfViewSet(BaseFeedCollectionViewSet):
    """
    A viewset for the FeedShelf class.
    """
    queryset = FeedShelf.objects.all()
    serializer_class = FeedShelfSerializer


class FeedShelfPublishView(CORSMixin, APIView):
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
    permission_classes = [GroupPermission('Feed', 'Curate')]
    cors_allowed_methods = ('delete', 'put',)

    def get_object(self, pk):
        if pk.isdigit():
            return FeedShelf.objects.get(pk=pk)
        else:
            return FeedShelf.objects.get(slug=pk)

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
        return response.Response(FeedItemSerializer(feed_item).data,
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


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()


class FeedCollectionImageViewSet(CollectionImageViewSet):
    queryset = FeedCollection.objects.all()


class FeedShelfImageViewSet(CollectionImageViewSet):
    queryset = FeedShelf.objects.all()


class BaseFeedESView(CORSMixin, APIView):
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
        if hasattr(feed_element, 'app'):
            return [feed_element.app]
        return feed_element.apps

    def get_app_ids_all(self, feed_elements):
        app_ids = []
        for elm in feed_elements:
            app_ids += self.get_app_ids(elm)
        return app_ids

    def mget_apps(self, app_ids):
        """
        Takes a list of app_ids. Does an ES mget.
        Returns an app_map for serializer context.
        """
        app_map = {}
        es = WebappIndexer.get_es()
        apps = es.mget(body={'ids': app_ids}, index=WebappIndexer.get_index(),
                       doc_type=WebappIndexer.get_mapping_type_name())
        for app in apps['docs']:
            # Store the apps to attach to feed elements later.
            app = app['_source']
            app_map[app['id']] = app
        return app_map


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
        ctx = {'app_map': self.mget_apps(self.get_app_ids_all(feed_elements)),
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
    - a mget to deserialize apps
    """
    authentication_classes = []
    cors_allowed_methods = ('get',)
    paginator_class = ESPaginator
    permission_classes = []

    def get_es_feed_query(self, sq, region=mkt.regions.RESTOFWORLD.id,
                          carrier=None):
        """
        Build ES query for feed.
        Weights on region and carrier if passed in.
        Orders by FeedItem.order.
        Operator shelf always on top if region and carrier passed in.

        region -- region ID (integer)
        carrier -- carrier ID (integer)
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
            return sq.query('function_score',
                            functions=[ordering_fn],
                            filter=region_filter)

        return sq.query(
            'function_score',
            functions=[boost_fn, ordering_fn],
            filter=es_filter.Bool(
                must=[es_filter.Term(region=region)],
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

    def _get(self, request, *args, **kwargs):
        es = FeedItemIndexer.get_es()

        # Parse carrier and region.
        q = request.QUERY_PARAMS
        region = request.REGION.id
        carrier = None
        if q.get('carrier') and q['carrier'] in mkt.carriers.CARRIER_MAP:
            carrier = mkt.carriers.CARRIER_MAP[q['carrier']].id

        # Fetch FeedItems.
        sq = self.get_es_feed_query(FeedItemIndexer.search(using=es),
                                    region=region, carrier=carrier)
        feed_items = self.paginate_queryset(sq)

        # No items returned; try to fall back to RoW.
        if not feed_items:
            world_sq = self.get_es_feed_query(FeedItemIndexer.search(using=es))
            world_feed_items = self.paginate_queryset(world_sq)

            # No RoW feed items, either. Let's 404.
            if not world_feed_items:
                world_meta = mkt.api.paginator.CustomPaginationSerializer(
                    world_feed_items,
                    context={'request': request}).data['meta']
                return response.Response({'meta': world_meta, 'objects': []},
                                         status=status.HTTP_404_NOT_FOUND)

            # Return RoW items.
            else:
                feed_items = world_feed_items

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
        for feed_elm in sq.execute().hits:
            # Store the feed elements to attach to FeedItems later.
            feed_element_map[feed_elm['item_type']][feed_elm['id']] = feed_elm
            # Store the apps to retrieve later.
            apps += self.get_app_ids(feed_elm)

        # Fetch apps to attach to feed elements later (with mget).
        app_map = self.mget_apps(apps)

        # Super serialize.
        feed_items = FeedItemESSerializer(feed_items, many=True, context={
            'app_map': app_map,
            'feed_element_map': feed_element_map,
            'request': request
        }).data

        return response.Response({'meta': meta, 'objects': feed_items},
                                 status=status.HTTP_200_OK)

    def get(self, request, *args, **kwargs):
        with statsd.timer('mkt.feed.view'):
            return self._get(request, *args, **kwargs)


class FeedElementGetView(BaseFeedESView):
    """
    Fetches individual feed elements from ES.
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
            'app_map': self.mget_apps(self.get_app_ids(feed_element)),
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
            'app_map': self.mget_apps(self.get_app_ids_all(feed_elements)),
            'request': request
        }, many=True).data

        return response.Response({'meta': meta, 'objects': objects},
                                 status=status.HTTP_200_OK)
