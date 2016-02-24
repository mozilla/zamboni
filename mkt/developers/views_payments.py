import json
import urllib

import commonware
import mkt
from django import http
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from lib.pay_server import client
from mkt.constants import PLATFORMS_NAMES
from mkt.constants.payments import PROVIDER_BANGO
from mkt.developers import forms, forms_payments
from mkt.developers.decorators import dev_required
from mkt.site.utils import render
from slumber.exceptions import HttpClientError


log = commonware.log.getLogger('z.devhub')


@dev_required(owner_for_post=True, webapp=True)
def payments(request, addon_id, addon, webapp=False):
    premium_form = forms_payments.PremiumForm(
        request.POST or None, request=request, addon=addon,
        user=request.user)

    region_form = forms.RegionForm(
        request.POST or None, product=addon, request=request)

    if request.method == 'POST':

        if region_form.is_valid() and premium_form.is_valid():
            region_form.save()
            premium_form.save()
            messages.success(request, _('Changes successfully saved.'))
            return redirect(addon.get_dev_url('payments'))

    return render(request, 'developers/payments/premium.html',
                  {'addon': addon, 'webapp': webapp,
                   'region_form': region_form,
                   'is_paid': (addon.premium_type in mkt.ADDON_PREMIUMS or
                               addon.premium_type == mkt.ADDON_FREE_INAPP),
                   'form': premium_form,
                   'PLATFORMS_NAMES': PLATFORMS_NAMES})


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
