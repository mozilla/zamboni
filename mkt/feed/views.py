import string

from django.conf import settings
from django.db.models import Q

from elasticsearch_dsl import filter as es_filter
from elasticsearch_dsl import function as es_function
from elasticsearch_dsl import F, query, Search
from rest_framework import response, status, viewsets
from rest_framework.exceptions import ParseError
from rest_framework.filters import BaseFilterBackend, OrderingFilter
from rest_framework.views import APIView

import mkt
import mkt.feed.constants as feed
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import (CORSMixin, MarketplaceView, SlugOrIdMixin)
from mkt.collections.views import CollectionImageViewSet
from mkt.feed.indexers import (FeedAppIndexer, FeedBrandIndexer,
                               FeedCollectionIndexer, FeedItemIndexer,
                               FeedShelfIndexer)
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Webapp

from .authorization import FeedAuthorization
from .constants import FEED_TYPE_SHELF
from .models import FeedApp, FeedBrand, FeedCollection, FeedItem, FeedShelf
from .serializers import (FeedAppSerializer, FeedBrandSerializer,
                          FeedCollectionSerializer, FeedItemSerializer,
                          FeedItemESSerializer, FeedShelfSerializer)


class BaseFeedCollectionViewSet(CORSMixin, SlugOrIdMixin, MarketplaceView,
                                viewsets.ModelViewSet):
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
        FeedItem.get_indexer().index_ids(feed_item_ids)

        return response.Response(status=status.HTTP_201_CREATED)


class FeedAppViewSet(CORSMixin, MarketplaceView, SlugOrIdMixin,
                     viewsets.ModelViewSet):
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
    Create a FeedItem for a FeedShelf with respective carrier/region pair.
    Deletes any currently existing FeedItems with the carrier/region pair to
    effectively "unpublish" it since only one shelf can be toggled at a time
    for a carrier/region.
    """
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Feed', 'Curate')]
    cors_allowed_methods = ('put',)

    def put(self, request, *args, **kwargs):
        pk = self.kwargs['pk']
        try:
            if pk.isdigit():
                shelf = FeedShelf.objects.get(pk=pk)
            else:
                shelf = FeedShelf.objects.get(slug=pk)
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


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()


class FeedCollectionImageViewSet(CollectionImageViewSet):
    queryset = FeedCollection.objects.all()


class FeedShelfImageViewSet(CollectionImageViewSet):
    queryset = FeedShelf.objects.all()


class FeedElementSearchView(CORSMixin, APIView):
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
            'slop': 4,
        }

    def get(self, request, *args, **kwargs):
        q = request.GET.get('q')

        match_query = (
            query.Q('match', slug=self._phrase(q)),
            query.Q('match', type=self._phrase(q)),
        )
        fuzzy_query = match_query + (query.Q('fuzzy', search_names=q),)

        feed_app_ids = [
            hit.id for hit in FeedAppIndexer.search().query(
                query.Bool(should=fuzzy_query)).execute().hits]

        feed_brand_ids = [
            hit.id for hit in FeedBrandIndexer.search().query(
                query.Bool(should=match_query)).execute().hits]

        feed_collection_ids = [
            hit.id for hit in FeedCollectionIndexer.search().query(
                query.Bool(should=fuzzy_query)).execute().hits]

        feed_shelf_ids = [
            hit.id for hit in FeedShelfIndexer.search().query(
                query.Bool(should=(
                    query.Q('fuzzy', search_names=q),
                    query.Q('fuzzy', slug=q),
                    query.Q('prefix', carrier=q),
                    query.Q('term', region=q)))).execute().hits]

        # Dehydrate.
        apps = FeedApp.objects.filter(id__in=feed_app_ids)
        brands = FeedBrand.objects.filter(id__in=feed_brand_ids)
        colls = FeedCollection.objects.filter(id__in=feed_collection_ids)
        shelves = FeedShelf.objects.filter(id__in=feed_shelf_ids)

        # Serialize.
        ctx = {'request': request}
        apps = [FeedAppSerializer(app, context=ctx).data for app in apps]
        brands = [FeedBrandSerializer(brand, context=ctx).data
                  for brand in brands]
        collections = [FeedCollectionSerializer(coll, context=ctx).data
                       for coll in colls]
        shelves = [FeedShelfSerializer(shelf, context=ctx).data
                   for shelf in shelves]

        # Return.
        return response.Response({
            'apps': apps,
            'brands': brands,
            'collections': collections,
            'shelves': shelves
        })


class FeedView(CORSMixin, APIView):
    """
    Streamlined view for a feed, separating operator shelves for ease of
    consumer display.
    """
    authentication_classes = []
    permission_classes = []
    cors_allowed_methods = ('get',)

    def get_es_feed_query(self, region=mkt.regions.RESTOFWORLD.id,
                          carrier=None):
        """
        Build ES query for feed.
        Weights on region and carrier if passed in.
        Operator shelf on top if region and carrier passed in.

        region -- region ID (integer)
        carrier -- carrier ID (integer)
        """
        # Filter by only region.
        region_filter = es_filter.Bool(must=[es_filter.Term(region=region)])
        if carrier is None:
            return region_filter.to_dict()  # Why doesn't work w/o to_dict()?

        # Filter by both region and carrier.
        shelf_filter = es_filter.Term(item_type=feed.FEED_TYPE_SHELF)

        # Boost shelf to top.
        functions = [es_function.BoostFactor(value=10000.0,
                                             filter=shelf_filter)]

        # Exclude shelves that may match the region, but NOT the carrier.
        bad_shelf_filter = es_filter.Bool(
            must=[shelf_filter],
            must_not=[es_filter.Term(carrier=carrier)])
        shelf_filter = es_filter.Bool(must_not=[bad_shelf_filter])

        return query.FunctionScore(functions=functions,
                                   filter=region_filter + shelf_filter)

    def get_es_feed_element_query(self, feed_items):
        """
        From a list of FeedItems with normalized feed element IDs,
        return an ES query that fetches the feed elements for each feed item.
        """
        filters = []
        for feed_item in feed_items:
            item_type = feed_item['item_type']
            filters.append(es_filter.Bool(must=[
                es_filter.Term(id=feed_item[item_type]),
                es_filter.Term(item_type=item_type)
            ]))

        return es_filter.Bool(should=filters)

    def get(self, request, *args, **kwargs):
        es = FeedItemIndexer.get_es()

        # Parse carrier and region.
        q = request.QUERY_PARAMS
        region = request.REGION.id
        carrier = None
        if q.get('carrier') and q['carrier'] in mkt.carriers.CARRIER_MAP:
            carrier = mkt.carriers.CARRIER_MAP[q['carrier']].id

        # Fetch FeedItems.
        sq = self.get_es_feed_query(region=region, carrier=carrier)
        feed_items = FeedItemIndexer.search(using=es).query(sq).execute().hits
        if not feed_items:
            # Fallback to RoW.
            sq = self.get_es_feed_query()
            feed_items = (FeedItemIndexer.search(using=es).query(sq)
                                                          .execute().hits)
            if not feed_items:
                return response.Response({'objects': []},
                                         status=status.HTTP_404_NOT_FOUND)

        # Set up serializer context and index name.
        apps = []
        feed_element_map = {
            feed.FEED_TYPE_APP: {},
            feed.FEED_TYPE_BRAND: {},
            feed.FEED_TYPE_COLL: {},
            feed.FEED_TYPE_SHELF: {},
        }
        index = [
            settings.ES_INDEXES['mkt_feed_app'],
            settings.ES_INDEXES['mkt_feed_brand'],
            settings.ES_INDEXES['mkt_feed_collection'],
            settings.ES_INDEXES['mkt_feed_shelf']
        ]

        # Fetch feed elements to attach to FeedItems later.
        sq = self.get_es_feed_element_query(feed_items)
        feed_elms = Search(using=es, index=index).filter(sq).execute().hits
        for feed_elm in feed_elms:
            # Store the feed elements to attach to FeedItems later.
            feed_element_map[feed_elm['item_type']][feed_elm['id']] = feed_elm
            # Store the apps to retrieve later.
            if feed_elm.get('app'):
                apps.append(feed_elm['app'])
            elif feed_elm.get('apps'):
                apps += feed_elm['apps']

        # Fetch apps to attach to feed elements later (with mget).
        app_map = {}
        apps = es.mget(body={'ids': apps}, index=WebappIndexer.get_index(),
                       doc_type=WebappIndexer.get_mapping_type_name())
        for app in apps['docs']:
            # Store the apps to attach to feed elements later.
            app = app['_source']
            app_map[app['id']] = app

        # Super serialize.
        feed_items = FeedItemESSerializer(feed_items, many=True, context={
            'app_map': app_map,
            'feed_element_map': feed_element_map,
            'request': request
        }).data

        return response.Response({'objects': feed_items},
                                 status=status.HTTP_200_OK)
