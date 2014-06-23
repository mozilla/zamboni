from django.db.models import Q

from elasticutils.contrib.django import S
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
                               FeedCollectionIndexer, FeedShelfIndexer)
from mkt.webapps.models import Webapp

from .authorization import FeedAuthorization
from .models import FeedApp, FeedBrand, FeedCollection, FeedItem, FeedShelf
from .serializers import (FeedAppSerializer, FeedBrandSerializer,
                          FeedCollectionSerializer, FeedItemSerializer,
                          FeedShelfSerializer)


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
        if q.get('region'):
            region_id =mkt.regions.REGIONS_DICT[q['region']].id
            qs = qs.filter(region=region_id)

        # Exclude feed items that specify carrier but do not match carrier.
        if q.get('carrier'):
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


class FeedAppImageViewSet(CollectionImageViewSet):
    queryset = FeedApp.objects.all()


class FeedCollectionImageViewSet(CollectionImageViewSet):
    queryset = FeedCollection.objects.all()


class FeedShelfImageViewSet(CollectionImageViewSet):
    queryset = FeedShelf.objects.all()


class FeedBrandViewSet(BaseFeedCollectionViewSet):
    """
    A viewset for the FeedBrand class, a type of collection that allows editors
    to quickly create content without involving localizers.
    """
    serializer_class = FeedBrandSerializer
    queryset = FeedBrand.objects.all()


class FeedCollectionViewSet(BaseFeedCollectionViewSet):
    """
    A viewset for the FeedCollection class.
    """
    serializer_class = FeedCollectionSerializer
    queryset = FeedCollection.objects.all()

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
    serializer_class = FeedShelfSerializer
    queryset = FeedShelf.objects.all()


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

    def _fuzzy(self, q):
        return {
            'query': q,
            'type': 'fuzzy',
            'fuzziness': 4,
        }

    def get(self, request, *args, **kwargs):
        q = request.GET.get('q')

        # Gather.
        query = {
            'slug__match': self._phrase(q),
            'type__match': self._phrase(q),
            'should': True
        }
        feed_app_ids = ([pk[0] for pk in S(FeedAppIndexer).query(
            name__match=self._fuzzy(q), **query).values_list('id')])
        feed_brand_ids = [pk[0] for pk in S(FeedBrandIndexer).query(
            **query).values_list('id')]
        feed_collection_ids = ([pk[0] for pk in S(FeedCollectionIndexer).query(
            name__match=self._fuzzy(q), **query).values_list('id')])
        feed_shelf_ids = ([pk[0] for pk in S(FeedShelfIndexer).query(
            name__match=self._fuzzy(q), slug__match=self._fuzzy(q),
            carrier__prefix=q, region=q, should=True).values_list('id')])

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
