import calendar
import time
import uuid

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import Http404

import commonware.log
from jingo.helpers import urlparams
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

import mkt
from lib.cef_loggers import app_pay_cef
from mkt.api.authentication import (RestAnonymousAuthentication,
                                    RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AllowReadOnly, AnyOf, GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView
from mkt.constants.regions import RESTOFWORLD
from mkt.purchase.models import Contribution
from mkt.receipts.utils import create_inapp_receipt
from mkt.site.mail import send_mail_jinja
from mkt.site.helpers import absolutify
from mkt.webpay.forms import FailureForm, PrepareInAppForm, PrepareWebAppForm
from mkt.webpay.models import ProductIcon
from mkt.webpay.serializers import (ContributionSerializer,
                                    ProductIconSerializer)
from mkt.webpay.webpay_jwt import (get_product_jwt, InAppProduct,
                                   sign_webpay_jwt, SimulatedInAppProduct,
                                   WebAppProduct)

from . import tasks


log = commonware.log.getLogger('z.webpay')


class PreparePayWebAppView(CORSMixin, MarketplaceView, GenericAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [IsAuthenticated]
    cors_allowed_methods = ['post']
    cors_allowed_headers = ('content-type', 'accept', 'x-fxpay-version')
    serializer_class = ContributionSerializer

    def post(self, request, *args, **kwargs):
        form = PrepareWebAppForm(request.DATA)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

        app = form.cleaned_data['app']

        region = getattr(request, 'REGION', None)
        if region:
            enabled_regions = app.get_price_region_ids()
            region_can_purchase = region.id in enabled_regions
            restofworld_can_purchase = RESTOFWORLD.id in enabled_regions

            if not region_can_purchase and not restofworld_can_purchase:
                log.info('Region {0} is not in {1}; '
                         'restofworld purchases are inactive'
                         .format(region.id, enabled_regions))
                return Response(
                    {'reason': 'Payments are restricted for this region'},
                    status=status.HTTP_403_FORBIDDEN)

        if app.is_premium() and app.has_purchased(request._request.user):
            log.info('Already purchased: {0}'.format(app.pk))
            return Response({'reason': u'Already purchased app.'},
                            status=status.HTTP_409_CONFLICT)

        app_pay_cef.log(request._request, 'Preparing JWT', 'preparing_jwt',
                        'Preparing JWT for: {0}'.format(app.pk), severity=3)

        log.debug('Starting purchase of app: {0} by user: {1}'.format(
            app.pk, request._request.user))

        contribution = Contribution.objects.create(
            addon_id=app.pk,
            amount=app.get_price(region=request._request.REGION.id),
            paykey=None,
            price_tier=app.premium.price,
            source=request._request.REQUEST.get('src', ''),
            source_locale=request._request.LANG,
            type=mkt.CONTRIB_PENDING,
            user=request._request.user,
            uuid=str(uuid.uuid4()),
        )

        log.debug('Storing contrib for uuid: {0}'.format(contribution.uuid))

        token = get_product_jwt(WebAppProduct(app), contribution)

        return Response(token, status=status.HTTP_201_CREATED)


class PreparePayInAppView(CORSMixin, MarketplaceView, GenericAPIView):
    authentication_classes = []
    permission_classes = []
    cors_allowed_methods = ['post']
    cors_allowed_headers = ('content-type', 'accept', 'x-fxpay-version')
    serializer_class = ContributionSerializer

    def post(self, request, *args, **kwargs):
        form = PrepareInAppForm(request.DATA)
        if not form.is_valid():
            app_pay_cef.log(
                request._request,
                'Preparing InApp JWT Failed',
                'preparing_inapp_jwt_failed',
                'Preparing InApp JWT Failed error: {0}'.format(form.errors),
                severity=3
            )
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

        inapp = form.cleaned_data['inapp']

        app_pay_cef.log(
            request._request,
            'Preparing InApp JWT',
            'preparing_inapp_jwt',
            'Preparing InApp JWT for: {0}'.format(inapp.pk), severity=3
        )

        log.debug('Starting purchase of in app: {0}'.format(inapp.pk))

        contribution = Contribution.objects.create(
            addon_id=inapp.webapp and inapp.webapp.pk,
            inapp_product=inapp,
            # In-App payments are unauthenticated so we have no user
            # and therefore can't determine a meaningful region.
            amount=None,
            paykey=None,
            price_tier=inapp.price,
            source=request._request.REQUEST.get('src', ''),
            source_locale=request._request.LANG,
            type=mkt.CONTRIB_PENDING,
            user=None,
            uuid=str(uuid.uuid4()),
        )

        log.info('Storing contrib for uuid: {0}'.format(contribution.uuid))

        if inapp.simulate:
            log.info('Preparing in-app JWT simulation for {i}'
                     .format(i=inapp))
            product = SimulatedInAppProduct(inapp)
        else:
            log.info('Preparing in-app JWT for {i}'.format(i=inapp))
            product = InAppProduct(inapp)
        token = get_product_jwt(product, contribution)

        return Response(token, status=status.HTTP_201_CREATED)


class StatusPayView(CORSMixin, MarketplaceView, GenericAPIView):
    """
    Get the status of a contribution (transaction) by UUID.

    This is used by the Marketplace or third party apps to check
    the fulfillment of a purchase. It does not require authentication
    so that in-app payments can work from third party apps.
    """
    authentication_classes = []
    permission_classes = []
    cors_allowed_methods = ['get']
    cors_allowed_headers = ('content-type', 'accept', 'x-fxpay-version')
    queryset = Contribution.objects.filter(type=mkt.CONTRIB_PURCHASE)
    lookup_field = 'uuid'

    def get_object(self):
        try:
            obj = super(StatusPayView, self).get_object()
        except Http404:
            # Anything that's not correct will be raised as a 404 so that it's
            # harder to iterate over contribution values.
            log.info('Contribution not found')
            return None

        return obj

    def get(self, request, *args, **kwargs):
        self.object = contrib = self.get_object()
        data = {'status': 'complete' if self.object else 'incomplete',
                'receipt': None}
        if getattr(contrib, 'inapp_product', None):
            data['receipt'] = create_inapp_receipt(contrib)
        return Response(data)


class FailureNotificationView(MarketplaceView, GenericAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Transaction', 'NotifyFailure')]
    queryset = Contribution.objects.filter(uuid__isnull=False)

    def patch(self, request, *args, **kwargs):
        form = FailureForm(request.DATA)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

        obj = self.get_object()
        data = {
            'transaction_id': obj,
            'transaction_url': absolutify(
                urlparams(reverse('mkt.developers.transactions'),
                          transaction_id=obj.uuid)),
            'url': form.cleaned_data['url'],
            'retries': form.cleaned_data['attempts']}
        owners = obj.addon.authors.values_list('email', flat=True)
        send_mail_jinja('Payment notification failure.',
                        'webpay/failure.txt',
                        data, recipient_list=owners)
        return Response(status=status.HTTP_202_ACCEPTED)


class ProductIconViewSet(CORSMixin, MarketplaceView, ListModelMixin,
                         RetrieveModelMixin, GenericViewSet):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication,
                              RestAnonymousAuthentication]
    permission_classes = [AnyOf(AllowReadOnly,
                                GroupPermission('ProductIcon', 'Create'))]
    queryset = ProductIcon.objects.all()
    serializer_class = ProductIconSerializer
    cors_allowed_methods = ['get', 'post']
    filter_fields = ('ext_url', 'ext_size', 'size')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.DATA)
        if serializer.is_valid():
            log.info('Resizing product icon %s @ %s to %s for webpay' % (
                serializer.data['ext_url'],
                serializer.data['ext_size'],
                serializer.data['size']))
            tasks.fetch_product_icon.delay(serializer.data['ext_url'],
                                           serializer.data['ext_size'],
                                           serializer.data['size'])
            return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes((AllowAny,))
def sig_check(request):
    """
    Returns a signed JWT to use for signature checking.

    This is for Nagios checks to ensure that Marketplace's
    signed tokens are valid when processed by Webpay.
    """
    issued_at = calendar.timegm(time.gmtime())
    req = {
        'iss': settings.APP_PURCHASE_KEY,
        'typ': settings.SIG_CHECK_TYP,
        'aud': settings.APP_PURCHASE_AUD,
        'iat': issued_at,
        'exp': issued_at + 3600,  # expires in 1 hour
        'request': {}
    }
    return Response({'sig_check_jwt': sign_webpay_jwt(req)},
                    status=201)
