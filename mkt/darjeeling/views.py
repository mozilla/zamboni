from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.serializers import SerializerMethodField

from mkt.api.base import CORSMixin, MarketplaceView
from mkt.collections.models import Collection
from mkt.fireplace.api import (FireplaceCollectionMembershipField,
                               FireplaceESAppSerializer)


class FakeCollection(object):
    def __init__(self, pk):
        self.pk = pk


class DarjeelingESAppSerializer(FireplaceESAppSerializer):
    featured = SerializerMethodField('is_featured')

    class Meta(FireplaceESAppSerializer.Meta):
        fields = sorted(FireplaceESAppSerializer.Meta.fields + ['featured'])
        exclude = FireplaceESAppSerializer.Meta.exclude

    def is_featured(self, obj):
        collections = [c['id'] for c in obj.es_data.get('collection', [])]
        return self.context['featured_pk'] in collections


class DarjeelingCollectionMembershipField(FireplaceCollectionMembershipField):
    app_serializer_classes = {
        'es': DarjeelingESAppSerializer,
    }


class DarjeelingAppList(CORSMixin, MarketplaceView, ListAPIView):
    """
    Endpoint that darjeeling client consumes to fetch its app list. The list is
    actually made of 2 things:
    - One collection called "darjeeling-apps" containg all apps;
    - One collection called "darjeeling-featured" containing all homepage apps.

    The first list is returned directly (without pagination) and since the
    second one is just supposed to be a subset of the first, only the app ids
    are returned.
    """
    cors_allowed_methods = ['get']
    authentication_classes = []
    permission_classes = []

    def get_collection(self, slug):
        """
        Return a Fake Collection object with only the pk, for use with
        CollectionMembershipField. We can't simply do a Collection.objects.only
        query, because transforms get in the way (no_transforms doesn't remove
        translations atm)
        """
        pk = Collection.objects.filter(slug=slug).values_list('pk', flat=True)
        return FakeCollection(pk[0])

    def get_queryset(self):
        """
        Fetch (and directly serialize using fireplace serializer) all apps
        belonging to the 'all' collection by querying ES.
        """
        collection_all = self.get_collection('darjeeling-apps')
        membership = DarjeelingCollectionMembershipField(many=True)
        membership.context = self.get_serializer_context()
        membership.context['use-es-for-apps'] = True
        membership.context['featured_pk'] = (
            self.get_collection('darjeeling-featured').pk)
        return membership.field_to_native_es(collection_all, self.request)

    def list(self, request, *args, **kwargs):
        data = {}
        data['all'] = self.get_queryset()
        data['featured'] = [d['id'] for d in data['all'] if d['featured']]
        return Response(data)
