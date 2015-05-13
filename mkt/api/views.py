import json
import operator

from django.conf import settings
from django.http import Http404
from django.views import debug
from django.views.decorators.csrf import csrf_exempt

import commonware.log
import raven.base
import waffle
from cache_nuggets.lib import memoize
from rest_framework import generics
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import (BooleanField, CharField, ChoiceField,
                                        DecimalField, HyperlinkedIdentityField,
                                        HyperlinkedRelatedField,
                                        ModelSerializer)
from rest_framework.views import APIView
from rest_framework.viewsets import (GenericViewSet, ModelViewSet,
                                     ReadOnlyModelViewSet)

from lib.constants import ALL_CURRENCIES
from mkt.account.helpers import fxa_auth_info
from mkt.api.authentication import RestOAuthAuthentication
from mkt.api.authorization import AllowAppOwner, GroupPermission
from mkt.api.base import cors_api_view, CORSMixin, MarketplaceView
from mkt.api.fields import SlugChoiceField
from mkt.api.serializers import (CarrierSerializer, CategorySerializer,
                                 RegionSerializer)
from mkt.carriers import CARRIER_MAP, CARRIERS
from mkt.constants.categories import CATEGORY_CHOICES, CATEGORY_CHOICES_DICT
from mkt.constants.payments import PAYMENT_METHOD_CHOICES, PROVIDER_CHOICES
from mkt.constants.regions import (REGIONS_CHOICES_SLUG,
                                   REGIONS_LIST_SORTED_BY_NAME)
from mkt.prices.models import Price, PriceCurrency
from mkt.regions.utils import parse_region
from mkt.webapps.models import Webapp
from mkt.webapps.tasks import _update_manifest


log = commonware.log.getLogger('z.api')


class TestError(Exception):
    pass


class ErrorViewSet(MarketplaceView, GenericViewSet):
    permission_classes = (AllowAny,)

    def list(self, request, *args, **kwargs):
        # All this does is throw an error. This is used for testing
        # the error handling on dev servers.
        # See mkt.api.exceptions for the error handler code.
        raise TestError('This is a test.')


class CategoryViewSet(CORSMixin, MarketplaceView, ReadOnlyModelViewSet):
    cors_allowed_methods = ['get']
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    paginate_by = len(CATEGORY_CHOICES_DICT)

    def get_queryset(self, *args, **kwargs):
        return CATEGORY_CHOICES

    def get_object(self, *args, **kwargs):
        cat = CATEGORY_CHOICES_DICT.get(self.kwargs['pk'])
        if cat is None:
            raise Http404
        else:
            return self.kwargs['pk'], cat


class FlagSerializer(ModelSerializer):

    class Meta:
        model = waffle.models.Flag


class SwitchSerializer(ModelSerializer):

    class Meta:
        model = waffle.models.Switch


@memoize(prefix='config-settings')
def get_settings():
    safe = debug.get_safe_settings()
    _settings = ['SITE_URL']
    return dict([k, safe[k]] for k in _settings)


@cors_api_view(['GET'])
@permission_classes([AllowAny])
def site_config(request):
    """
    A resource that is designed to be exposed externally and contains
    settings or waffle flags that might be relevant to the client app.
    """
    def serialized_data(cls):
        as_list = cls(cls.Meta.model.objects.all().order_by('name'),
                      many=True).data
        return dict((d['name'], d) for d in as_list)

    # For Commonplace, we don't need settings or version, we just want a simple
    # list of active waffle switches, we don't even care about flags.
    if request.GET.get('serializer') == 'commonplace':
        data = {
            'waffle': {
                'switches': list(
                    waffle.models.Switch.objects.filter(active=True)
                                        .values_list('name', flat=True))
            }
        }
    else:
        data = {
            'settings': get_settings(),
            'version': getattr(settings, 'BUILD_ID_JS', ''),
            'waffle': {
                'switches': serialized_data(SwitchSerializer),
                'flags': serialized_data(FlagSerializer)
            }
        }

    # Always include FxA info, all projects need it.
    fxa_auth_state, fxa_auth_url = fxa_auth_info()
    data['fxa'] = {
        'fxa_auth_state': fxa_auth_state,
        'fxa_auth_url': fxa_auth_url
    }
    return Response(data)


class RegionViewSet(CORSMixin, MarketplaceView, ReadOnlyModelViewSet):
    cors_allowed_methods = ['get']
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RegionSerializer
    paginate_by = len(REGIONS_CHOICES_SLUG)

    def get_queryset(self, *args, **kwargs):
        return REGIONS_LIST_SORTED_BY_NAME()

    def get_object(self, *args, **kwargs):
        region = parse_region(self.kwargs['pk'])
        if region is None:
            raise Http404
        else:
            return region


class CarrierViewSet(RegionViewSet):
    serializer_class = CarrierSerializer
    paginate_by = len(CARRIERS)

    def get_queryset(self, *args, **kwargs):
        return sorted(CARRIERS, key=operator.attrgetter('name'))

    def get_object(self, *args, **kwargs):
        return CARRIER_MAP.get(self.kwargs['pk'], None)


@cors_api_view(['GET'])
@permission_classes([AllowAny])
def error_reporter(request):
    request._request.CORS = ['GET']
    client = raven.base.Client(settings.SENTRY_DSN)
    error_data = json.loads(request.GET['sentry_data'])
    client.capture('raven.events.Exception', data=error_data)
    return Response(status=204)


class RefreshManifestViewSet(GenericViewSet, CORSMixin):
    model = Webapp
    permission_classes = [AllowAppOwner]
    cors_allowed_methods = ('post',)
    slug_lookup = 'app_slug'

    def detail_post(self, request, **kwargs):
        obj = self.get_object()
        self.check_object_permissions(request, obj)
        if obj.is_packaged:
            return Response(
                status=400,
                data={'reason': 'App is a packaged app.'})
        _update_manifest(obj.pk, True, {})
        return Response(status=204)


class EnumeratedField(ChoiceField):

    def from_native(self, value):
        for k, v in self.choices:
            if value == v:
                return k

    def to_native(self, key):
        for k, v in self.choices:
            if key == k:
                return v


class PriceTierSerializer(ModelSerializer):
    resource_uri = HyperlinkedIdentityField(view_name='price-tier-detail')
    active = BooleanField()
    name = CharField()
    method = EnumeratedField(PAYMENT_METHOD_CHOICES)
    price = DecimalField()

    class Meta:
        model = Price
        fields = ['resource_uri', 'active', 'name', 'method', 'price']


class PriceTierViewSet(generics.CreateAPIView,
                       generics.RetrieveUpdateDestroyAPIView,
                       ModelViewSet):
    permission_classes = [GroupPermission('Prices', 'Edit')]
    authentication_classes = [RestOAuthAuthentication]
    serializer_class = PriceTierSerializer
    model = Price


class PriceCurrencySerializer(ModelSerializer):
    resource_uri = HyperlinkedIdentityField(view_name='price-currency-detail')
    tier = HyperlinkedRelatedField(view_name='price-tier-detail')
    currency = ChoiceField(choices=ALL_CURRENCIES.items())
    carrier = SlugChoiceField(choices_dict=CARRIER_MAP,
                              required=False, empty=None)
    price = DecimalField()
    provider = EnumeratedField(PROVIDER_CHOICES)
    method = EnumeratedField(PAYMENT_METHOD_CHOICES)
    region = SlugChoiceField(choices_dict=dict(REGIONS_CHOICES_SLUG))
    paid = BooleanField()
    dev = BooleanField()

    class Meta:
        model = PriceCurrency
        fields = ['carrier', 'currency', 'dev', 'method', 'paid', 'price',
                  'provider', 'region', 'resource_uri', 'tier']


class PriceCurrencyViewSet(ModelViewSet):
    permission_classes = [GroupPermission('Prices', 'Edit')]
    authentication_classes = [RestOAuthAuthentication]
    serializer_class = PriceCurrencySerializer
    model = PriceCurrency
    filter_fields = ('tier', 'provider', 'currency', 'price')

    def post_save(self, obj, created):
        log.info('Price %s %s.' % (obj, 'created' if created else 'updated'))

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.delete()
        log.info('Price %s deleted.' % (obj,))
        return Response(status=204)


class EndpointRemoved(APIView):
    """
    View that always returns a 404.

    To be used when API endpoints are removed in newer versions of the API.
    """
    def dispatch(self, request, *args, **kwargs):
        raise Http404


endpoint_removed = csrf_exempt(EndpointRemoved.as_view())
