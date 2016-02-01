import functools
import json
import urllib

from django import http
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

import commonware
import jinja2
import waffle
from slumber.exceptions import HttpClientError
from django.utils.translation import ugettext as _
from waffle.decorators import waffle_switch

import mkt
from lib.crypto import generate_key
from lib.pay_server import client
from mkt.access import acl
from mkt.constants import PAID_PLATFORMS, PLATFORMS_NAMES
from mkt.constants.payments import (PAYMENT_METHOD_ALL, PAYMENT_METHOD_CARD,
                                    PAYMENT_METHOD_OPERATOR, PROVIDER_BANGO,
                                    PROVIDER_CHOICES)
from mkt.developers import forms, forms_payments
from mkt.developers.decorators import dev_required
from mkt.developers.models import CantCancel, PaymentAccount, UserInappKey
from mkt.developers.providers import get_provider, get_providers
from mkt.inapp.models import InAppProduct
from mkt.inapp.serializers import InAppProductForm
from mkt.prices.models import Price
from mkt.site.decorators import json_view, login_required, use_master
from mkt.site.utils import render
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('z.devhub')


@dev_required
@require_POST
def disable_payments(request, addon_id, addon):
    return redirect(addon.get_dev_url('payments'))


@dev_required(owner_for_post=True, webapp=True)
def payments(request, addon_id, addon, webapp=False):
    premium_form = forms_payments.PremiumForm(
        request.POST or None, request=request, addon=addon,
        user=request.user)

    region_form = forms.RegionForm(
        request.POST or None, product=addon, request=request)

    upsell_form = forms_payments.UpsellForm(
        request.POST or None, addon=addon, user=request.user)

    providers = get_providers()

    if 'form-TOTAL_FORMS' in request.POST:
        formset_data = request.POST
    else:
        formset_data = None
    account_list_formset = forms_payments.AccountListFormSet(
        data=formset_data,
        provider_data=[
            {'addon': addon, 'user': request.user, 'provider': provider}
            for provider in providers])

    if request.method == 'POST':

        active_forms = [premium_form, region_form, upsell_form]
        if formset_data is not None:
            active_forms.append(account_list_formset)

        success = all(form.is_valid() for form in active_forms)

        if success:
            region_form.save()

            try:
                premium_form.save()
            except client.Error as err:
                success = False
                log.error('Error setting payment information (%s)' % err)
                messages.error(
                    request, _(u'We encountered a problem connecting to the '
                               u'payment server.'))
                raise  # We want to see these exceptions!

            is_free_inapp = addon.premium_type == mkt.ADDON_FREE_INAPP
            is_now_paid = (addon.premium_type in mkt.ADDON_PREMIUMS or
                           is_free_inapp)

            # If we haven't changed to a free app, check the upsell.
            if is_now_paid and success:
                try:
                    if not is_free_inapp:
                        upsell_form.save()
                    if formset_data is not None:
                        account_list_formset.save()
                except client.Error as err:
                    log.error('Error saving payment information (%s)' % err)
                    messages.error(
                        request, _(u'We encountered a problem connecting to '
                                   u'the payment server.'))
                    success = False
                    raise  # We want to see all the solitude errors now.

        # If everything happened successfully, give the user a pat on the back.
        if success:
            messages.success(request, _('Changes successfully saved.'))
            return redirect(addon.get_dev_url('payments'))

    # TODO: refactor this (bug 945267)
    android_pay = waffle.flag_is_active(request, 'android-payments')
    desktop_pay = waffle.flag_is_active(request, 'desktop-payments')

    # If android payments is not allowed then firefox os must
    # be 'checked' and android-mobile and android-tablet should not be.
    invalid_paid_platform_state = []

    if not android_pay:
        # When android-payments is off...
        invalid_paid_platform_state += [('android-mobile', True),
                                        ('android-tablet', True),
                                        ('firefoxos', False)]

    if not desktop_pay:
        # When desktop-payments is off...
        invalid_paid_platform_state += [('desktop', True)]

    cannot_be_paid = (
        addon.premium_type == mkt.ADDON_FREE and
        any(premium_form.device_data['free-%s' % x] == y
            for x, y in invalid_paid_platform_state))

    try:
        tier_zero = Price.objects.get(price='0.00', active=True)
        tier_zero_id = tier_zero.pk
    except Price.DoesNotExist:
        tier_zero = None
        tier_zero_id = ''

    # Get the regions based on tier zero. This should be all the
    # regions with payments enabled.
    paid_region_ids_by_name = []
    if tier_zero:
        paid_region_ids_by_name = tier_zero.region_ids_by_name()

    platforms = PAID_PLATFORMS(request)
    paid_platform_names = [unicode(platform[1]) for platform in platforms]

    provider_regions = {}
    if tier_zero:
        provider_regions = tier_zero.provider_regions()

    return render(request, 'developers/payments/premium.html',
                  {'addon': addon, 'webapp': webapp, 'premium': addon.premium,
                   'form': premium_form, 'upsell_form': upsell_form,
                   'tier_zero_id': tier_zero_id, 'region_form': region_form,
                   'PLATFORMS_NAMES': PLATFORMS_NAMES,
                   'is_paid': (addon.premium_type in mkt.ADDON_PREMIUMS or
                               addon.premium_type == mkt.ADDON_FREE_INAPP),
                   'cannot_be_paid': cannot_be_paid,
                   'paid_platform_names': paid_platform_names,
                   'is_packaged': addon.is_packaged,
                   # Bango values
                   'account_list_forms': account_list_formset.forms,
                   'account_list_formset': account_list_formset,
                   # Waffles
                   'api_pricelist_url': reverse('price-list'),
                   'payment_methods': {
                       PAYMENT_METHOD_ALL: _('All'),
                       PAYMENT_METHOD_CARD: _('Credit card'),
                       PAYMENT_METHOD_OPERATOR: _('Carrier'),
                   },
                   'provider_lookup': dict(PROVIDER_CHOICES),
                   'all_paid_region_ids_by_name': paid_region_ids_by_name,
                   'providers': providers,
                   'provider_regions': provider_regions,
                   'enabled_provider_ids':
                       [acct.payment_account.provider
                           for acct in addon.all_payment_accounts()]
                   })


@login_required
@json_view
def payment_accounts(request):
    app_slug = request.GET.get('app-slug', '')
    if app_slug:
        app = Webapp.objects.get(app_slug=app_slug)
        app_name = app.name
    else:
        app_name = ''
    accounts = PaymentAccount.objects.filter(
        user=request.user,
        provider__in=[p.provider for p in get_providers()],
        inactive=False)

    def account(acc):
        def payment_account_names(app):
            account_names = [unicode(acc.payment_account)
                             for acc in app.all_payment_accounts()]
            return (unicode(app.name), account_names)

        addon_payment_accounts = acc.addonpaymentaccount_set.all()
        associated_apps = [apa.addon
                           for apa in addon_payment_accounts
                           if hasattr(apa, 'addon')]
        app_names = u', '.join(unicode(app.name) for app in associated_apps)
        app_payment_accounts = json.dumps(dict([payment_account_names(app)
                                                for app in associated_apps]))
        provider = acc.get_provider()
        data = {
            'account-url': reverse('mkt.developers.provider.payment_account',
                                   args=[acc.pk]),
            'agreement-url': acc.get_agreement_url(),
            'agreement': 'accepted' if acc.agreed_tos else 'rejected',
            'current-app-name': jinja2.escape(app_name),
            'app-names': jinja2.escape(app_names),
            'app-payment-accounts': jinja2.escape(app_payment_accounts),
            'delete-url': reverse(
                'mkt.developers.provider.delete_payment_account',
                args=[acc.pk]),
            'id': acc.pk,
            'name': jinja2.escape(unicode(acc)),
            'provider': provider.name,
            'provider-full': unicode(provider.full),
            'shared': acc.shared,
            'portal-url': provider.get_portal_url(app_slug)
        }
        return data

    return map(account, accounts)


@login_required
def payment_accounts_form(request):
    webapp = get_object_or_404(Webapp, app_slug=request.GET.get('app_slug'))
    provider = get_provider(name=request.GET.get('provider'))
    account_list_formset = forms_payments.AccountListFormSet(
        provider_data=[
            {'user': request.user, 'addon': webapp, 'provider': p}
            for p in get_providers()])
    account_list_form = next(form for form in account_list_formset.forms
                             if form.provider.name == provider.name)
    return render(request,
                  'developers/payments/includes/bango_accounts_form.html',
                  {'account_list_form': account_list_form})


@use_master
@require_POST
@login_required
@json_view
def payments_accounts_add(request):
    provider = get_provider(name=request.POST.get('provider'))
    form = provider.forms['account'](request.POST)
    if not form.is_valid():
        return json_view.error(form.errors)

    try:
        obj = provider.account_create(request.user, form.cleaned_data)
    except HttpClientError as e:
        log.error('Client error create {0} account: {1}'.format(
            provider.name, e))
        return http.HttpResponseBadRequest(json.dumps(e.content))

    return {'pk': obj.pk, 'agreement-url': obj.get_agreement_url()}


@use_master
@login_required
@json_view
def payments_account(request, id):
    account = get_object_or_404(PaymentAccount, pk=id, user=request.user)
    provider = account.get_provider()
    if request.POST:
        form = provider.forms['account'](request.POST, account=account)
        if form.is_valid():
            form.save()
        else:
            return json_view.error(form.errors)

    return provider.account_retrieve(account)


@use_master
@require_POST
@login_required
def payments_accounts_delete(request, id):
    account = get_object_or_404(PaymentAccount, pk=id, user=request.user)
    try:
        account.cancel(disable_refs=True)
    except CantCancel:
        log.info('Could not cancel account.')
        return http.HttpResponse('Cannot cancel account', status=409)

    log.info('Account cancelled: %s' % id)
    return http.HttpResponse('success')


@login_required
def in_app_keys(request):
    """
    Allows developers to get a simulation-only key for in-app payments.

    This key cannot be used for real payments.
    """
    keys = UserInappKey.objects.filter(
        solitude_seller__user=request.user
    )

    # TODO(Kumar) support multiple test keys. For now there's only one.
    key = None
    key_public_id = None

    if keys.exists():
        key = keys.get()

        # Attempt to retrieve the public id from solitude
        try:
            key_public_id = key.public_id()
        except HttpClientError, e:
            messages.error(request,
                           _('A server error occurred '
                             'when retrieving the application key.'))
            log.exception('Solitude connection error: {0}'.format(e.message))

    if request.method == 'POST':
        if key:
            key.reset()
            messages.success(request, _('Secret was reset successfully.'))
        else:
            UserInappKey.create(request.user)
            messages.success(request,
                             _('Key and secret were created successfully.'))
        return redirect(reverse('mkt.developers.apps.in_app_keys'))

    return render(request, 'developers/payments/in-app-keys.html',
                  {'key': key, 'key_public_id': key_public_id})


@login_required
def in_app_key_secret(request, pk):
    key = (UserInappKey.objects
           .filter(solitude_seller__user=request.user, pk=pk))
    if not key.count():
        # Either the record does not exist or it's not owned by the
        # logged in user.
        return http.HttpResponseForbidden()
    return http.HttpResponse(key.get().secret())


def require_in_app_payments(render_view):
    @functools.wraps(render_view)
    def inner(request, addon_id, addon, *args, **kwargs):
        setup_url = reverse('mkt.developers.apps.payments',
                            args=[addon.app_slug])
        if addon.premium_type not in mkt.ADDON_INAPPS:
            messages.error(
                request,
                _('Your app is not configured for in-app payments.'))
            return redirect(setup_url)
        if not addon.has_payment_account():
            messages.error(request, _('No payment account for this app.'))
            return redirect(setup_url)

        # App is set up for payments; render the view.
        return render_view(request, addon_id, addon, *args, **kwargs)
    return inner


@login_required
@dev_required(webapp=True)
@require_in_app_payments
def in_app_payments(request, addon_id, addon, webapp=True, account=None):
    return render(request, 'developers/payments/in-app-payments.html',
                  {'addon': addon})


@waffle_switch('in-app-products')
@login_required
@dev_required(webapp=True)
@require_in_app_payments
def in_app_products(request, addon_id, addon, webapp=True, account=None):
    owner = acl.check_addon_ownership(request, addon)
    products = addon.inappproduct_set.all()
    new_product = InAppProduct(webapp=addon)
    form = InAppProductForm()

    if addon.origin:
        inapp_origin = addon.origin
    elif addon.guid:
        # Derive a marketplace specific origin out of the GUID.
        # This is for apps that do not specify a custom origin.
        inapp_origin = 'marketplace:{}'.format(addon.guid)
    else:
        # Theoretically this is highly unlikely. A hosted app will
        # always have a domain and a packaged app will always have
        # a generated GUID.
        raise TypeError(
            'Cannot derive origin: no declared origin, no GUID')

    list_url = _fix_origin_link(reverse('in-app-products-list',
                                        kwargs={'origin': inapp_origin}))
    detail_url = _fix_origin_link(reverse('in-app-products-detail',
                                          # {guid} is replaced in JS.
                                          kwargs={'origin': inapp_origin,
                                                  'guid': "{guid}"}))

    return render(request, 'developers/payments/in-app-products.html',
                  {'addon': addon, 'form': form, 'new_product': new_product,
                   'owner': owner, 'products': products, 'form': form,
                   'list_url': list_url, 'detail_url': detail_url,
                   'active_lang': request.LANG.lower()})


def _fix_origin_link(link):
    """
    Return a properly URL encoded link that might contain an app origin.

    App origins look like ``app://fxpay.allizom.org`` but Django does not
    encode the double slashes. This seems to cause a problem on our
    production web servers maybe because double slashes are normalized.
    See https://bugzilla.mozilla.org/show_bug.cgi?id=1065006
    """
    return link.replace('//', '%2F%2F')


@login_required
@dev_required(owner_for_post=True, webapp=True)
@require_in_app_payments
def in_app_config(request, addon_id, addon, webapp=True):
    """
    Allows developers to get a key/secret for doing in-app payments.
    """
    config = get_inapp_config(addon)

    owner = acl.check_addon_ownership(request, addon)
    if request.method == 'POST':
        # Reset the in-app secret for the app.
        (client.api.generic
               .product(config['resource_pk'])
               .patch(data={'secret': generate_key(48)}))
        messages.success(request, _('Changes successfully saved.'))
        return redirect(reverse('mkt.developers.apps.in_app_config',
                                args=[addon.app_slug]))

    return render(request, 'developers/payments/in-app-config.html',
                  {'addon': addon, 'owner': owner,
                   'seller_config': config})


@login_required
@dev_required(webapp=True)
@require_in_app_payments
def in_app_secret(request, addon_id, addon, webapp=True):
    config = get_inapp_config(addon)
    return http.HttpResponse(config['secret'])


def get_inapp_config(addon):
    """
    Returns a generic Solitude product, the app's in-app configuration.

    We use generic products in Solitude to represent an "app" that is
    enabled for in-app purchases.
    """
    if not addon.solitude_public_id:
        # If the view accessing this method uses all the right
        # decorators then this error won't be raised.
        raise ValueError('The app {a} has not yet been configured '
                         'for payments'.format(a=addon))
    return client.api.generic.product.get_object(
        public_id=addon.solitude_public_id)


@dev_required(webapp=True)
def bango_portal_from_addon(request, addon_id, addon, webapp=True):
    try:
        bango = addon.payment_account(PROVIDER_BANGO)
    except addon.PayAccountDoesNotExist:
        log.error('Bango portal not available for app {app} '
                  'with accounts {acct}'
                  .format(app=addon,
                          acct=list(addon.all_payment_accounts())))
        return http.HttpResponseForbidden()
    else:
        account = bango.payment_account

    if not ((addon.authors.filter(
             pk=request.user.pk,
             addonuser__role=mkt.AUTHOR_ROLE_OWNER).exists()) and
            (account.solitude_seller.user.id == request.user.id)):
        log.error(('User not allowed to reach the Bango portal; '
                   'pk=%s') % request.user.pk)
        return http.HttpResponseForbidden()

    return _redirect_to_bango_portal(account.account_id,
                                     'addon_id: %s' % addon_id)


def _redirect_to_bango_portal(package_id, source):
    try:
        bango_token = client.api.bango.login.post({'packageId':
                                                   int(package_id)})
    except HttpClientError as e:
        log.error('Failed to authenticate against Bango portal; %s' % source,
                  exc_info=True)
        return http.HttpResponseBadRequest(json.dumps(e.content))

    bango_url = '{base_url}{parameters}'.format(**{
        'base_url': settings.BANGO_BASE_PORTAL_URL,
        'parameters': urllib.urlencode({
            'authenticationToken': bango_token['authentication_token'],
            'emailAddress': bango_token['email_address'],
            'packageId': package_id,
            'personId': bango_token['person_id'],
        })
    })
    response = http.HttpResponse(status=204)
    response['Location'] = bango_url
    return response


# TODO(andym): move these into a DRF API.
@login_required
@json_view
def agreement(request, id):
    account = get_object_or_404(PaymentAccount, pk=id, user=request.user)
    provider = account.get_provider()
    if request.method == 'POST':
        return provider.terms_update(account)

    return provider.terms_retrieve(account)
