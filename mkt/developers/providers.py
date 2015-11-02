import os
import uuid
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.urlresolvers import reverse

import bleach
import commonware
from tower import ugettext_lazy as _

from lib.crypto import generate_key
# Because client is used in the classes, renaming here for clarity.
from lib.pay_server import client as pay_client
from mkt.constants.payments import ACCESS_PURCHASE
from mkt.constants.payments import PROVIDER_BANGO, PROVIDER_REFERENCE
from mkt.developers import forms_payments
from mkt.developers.models import PaymentAccount, SolitudeSeller
from mkt.developers.utils import uri_to_pk
from mkt.webpay.utils import make_external_id


root = 'developers/payments/includes/'

log = commonware.log.getLogger('z.devhub.providers')


def get_uuid(prefix=''):
    """
    Return a uuid for use in the payment flow. In debugging it prefixes
    the value of the uuid so its easier to spot in logs and such.
    """
    if settings.DEBUG:
        return prefix + str(uuid.uuid4())
    return str(uuid.uuid4())


def account_check(f):
    """
    Use this decorator on Provider methods to ensure that the account
    being passed into the method belongs to that provider.
    """
    def wrapper(self, *args, **kwargs):
        for arg in args:
            if (isinstance(arg, PaymentAccount) and
                    arg.provider != self.provider):
                raise ValueError('Wrong account {0} != {1}'
                                 .format(arg.provider, self.provider))
        return f(self, *args, **kwargs)
    return wrapper


class Provider(object):
    generic = pay_client.api.generic

    def account_create(self, user, form_data):
        raise NotImplementedError

    @account_check
    def account_retrieve(self, account):
        raise NotImplementedError

    @account_check
    def account_update(self, account, form_data):
        raise NotImplementedError

    @account_check
    def get_or_create_public_id(self, app):
        """
        Returns the Solitude public_id for this app if set
        otherwise creates one
        """
        if app.solitude_public_id is None:
            app.solitude_public_id = get_uuid('public')
            app.save()

        return app.solitude_public_id

    @account_check
    def get_or_create_generic_product(self, app, secret=None):
        product_data = {
            'public_id': self.get_or_create_public_id(app),
        }

        log.info('Checking generic seller exists: {0}'.format(product_data))
        try:
            generic = self.generic.product.get_object_or_404(**product_data)
        except ObjectDoesNotExist:
            seller_uuid = get_uuid('seller')
            seller = self.generic.seller.post(data={'uuid': seller_uuid})

            log.info(
                'Creating a new Generic Solitude '
                'Seller {seller_uuid} for app {app}'.format(
                    seller_uuid=seller_uuid,
                    app=app,
                )
            )

            product_data.update({
                'external_id': make_external_id(app),
                'seller': seller['resource_uri'],
                'secret': secret or generate_key(48),
                'access': ACCESS_PURCHASE,
            })
            generic = self.generic.product.post(data=product_data)

            log.info(
                'Creating a new Generic Solitude Product '
                '{public_id} for app {app}'.format(
                    public_id=product_data['public_id'],
                    app=app,
                )
            )

        return generic

    @account_check
    def product_create(self, account, app, secret):
        raise NotImplementedError

    def setup_seller(self, user):
        log.info('[User:{0}] Creating seller'.format(user.pk))
        return SolitudeSeller.create(user)

    def setup_account(self, **kw):
        log.info('[User:{0}] Created payment account (uri: {1})'
                 .format(kw['user'].pk, kw['uri']))
        kw.update({'seller_uri': kw['solitude_seller'].resource_uri,
                   'provider': self.provider})
        return PaymentAccount.objects.create(**kw)

    @account_check
    def terms_create(self, account):
        raise NotImplementedError

    @account_check
    def terms_retrieve(self, account):
        raise NotImplementedError

    def get_portal_url(self, app_slug=None):
        """
        Return a URL to the payment provider's portal.

        The URL can be an empty string if the provider
        doesn't have a portal.
        """
        return ''


class Bango(Provider):
    """
    The special Bango implementation.
    """
    bank_values = (
        'seller_bango', 'bankAccountPayeeName', 'bankAccountNumber',
        'bankAccountCode', 'bankName', 'bankAddress1', 'bankAddress2',
        'bankAddressZipCode', 'bankAddressIso'
    )
    client = pay_client.api.bango
    # This is at the new provider API.
    client_provider = pay_client.api.provider.bango
    forms = {
        'account': forms_payments.BangoPaymentAccountForm,
    }
    full = 'Bango'
    name = 'bango'
    package_values = (
        'adminEmailAddress', 'supportEmailAddress', 'financeEmailAddress',
        'paypalEmailAddress', 'vendorName', 'companyName', 'address1',
        'address2', 'addressCity', 'addressState', 'addressZipCode',
        'addressPhone', 'countryIso', 'currencyIso', 'vatNumber'
    )
    provider = PROVIDER_BANGO
    templates = {
        'add': os.path.join(root, 'add_payment_account_bango.html'),
        'edit': os.path.join(root, 'edit_payment_account_bango.html'),
    }

    def account_create(self, user, form_data):
        # Get the seller object.
        user_seller = self.setup_seller(user)

        # Get the data together for the package creation.
        package_values = dict((k, v) for k, v in form_data.items() if
                              k in self.package_values)
        # Dummy value since we don't really use this.
        package_values.setdefault('paypalEmailAddress', 'nobody@example.com')
        package_values['seller'] = user_seller.resource_uri

        log.info('[User:%s] Creating Bango package' % user)
        res = self.client.package.post(data=package_values)
        uri = res['resource_uri']

        # Get the data together for the bank details creation.
        bank_details_values = dict((k, v) for k, v in form_data.items() if
                                   k in self.bank_values)
        bank_details_values['seller_bango'] = uri

        log.info('[User:%s] Creating Bango bank details' % user)
        self.client.bank.post(data=bank_details_values)
        return self.setup_account(user=user,
                                  uri=res['resource_uri'],
                                  solitude_seller=user_seller,
                                  account_id=res['package_id'],
                                  name=form_data['account_name'])

    @account_check
    def account_retrieve(self, account):
        data = {'account_name': account.name}
        package_data = (self.client.package(uri_to_pk(account.uri))
                        .get(data={'full': True}))
        data.update((k, v) for k, v in package_data.get('full').items() if
                    k in self.package_values)
        return data

    @account_check
    def account_update(self, account, form_data):
        account.update(name=form_data.pop('account_name'))
        self.client.api.by_url(account.uri).patch(
            data=dict((k, v) for k, v in form_data.items() if
                      k in self.package_values))

    @account_check
    def product_create(self, account, app):
        secret = generate_key(48)
        generic = self.get_or_create_generic_product(app, secret=secret)
        product_uri = generic['resource_uri']
        data = {'seller_product': uri_to_pk(product_uri)}

        # There are specific models in solitude for Bango details.
        # These are SellerBango and SellerProductBango that store Bango
        # details such as the Bango Number.
        #
        # Solitude calls Bango to set up whatever it needs.
        try:
            res = self.client.product.get_object_or_404(**data)
        except ObjectDoesNotExist:
            # The product does not exist in Solitude so create it.
            res = self.client_provider.product.post(data={
                'seller_bango': account.uri,
                'seller_product': product_uri,
                'name': unicode(app.name),
                'packageId': account.account_id,
                'categoryId': 1,
                'secret': secret
            })

        return res['resource_uri']

    @account_check
    def terms_update(self, account):
        package = self.client.package(account.uri).get_object_or_404()
        account.update(agreed_tos=True)
        return self.client.sbi.post(data={
            'seller_bango': package['resource_uri']})

    @account_check
    def terms_retrieve(self, account):
        package = self.client.package(account.uri).get_object_or_404()
        res = self.client.sbi.get_object(data={
            'seller_bango': package['resource_uri']})
        if 'text' in res:
            res['text'] = bleach.clean(res['text'], tags=['h3', 'h4', 'br',
                                                          'p', 'hr'])
        return res

    def get_portal_url(self, app_slug=None):
        url = 'mkt.developers.apps.payments.bango_portal_from_addon'
        return reverse(url, args=[app_slug]) if app_slug else ''


class Reference(Provider):
    """
    The reference implementation provider. If another provider
    implements to the reference specification, then it should be able to
    just inherit from this with minor changes.
    """
    client = pay_client.api.provider.reference
    forms = {
        'account': forms_payments.ReferenceAccountForm,
    }
    full = unicode(_(u'Reference Implementation'))
    name = 'reference'
    provider = PROVIDER_REFERENCE
    templates = {
        'add': os.path.join(root, 'add_payment_account_reference.html'),
        'edit': os.path.join(root, 'edit_payment_account_reference.html'),
    }

    def account_create(self, user, form_data):
        user_seller = self.setup_seller(user)
        form_data.update({
            'seller': user_seller.resource_uri,
            'status': 'ACTIVE',
            'uuid': get_uuid('reference-seller')
        })
        name = form_data.pop('account_name')
        res = self.client.sellers.post(data=form_data)

        log.info('[User:%s] Creating Reference account' % user.pk)
        return self.setup_account(user=user,
                                  uri=res['resource_uri'],
                                  solitude_seller=user_seller,
                                  account_id=res['id'],
                                  name=name)

    @account_check
    def account_retrieve(self, account):
        data = {'account_name': account.name}
        data.update(self.client.sellers(account.account_id).get())
        log.info('Retreiving Reference account: %s' % account.pk)
        return data

    @account_check
    def account_update(self, account, form_data):
        account.update(name=form_data.pop('account_name'))
        self.client.sellers(account.account_id).put(form_data)
        log.info('Updating Reference account: %s' % account.pk)

    @account_check
    def product_create(self, account, app):
        secret = generate_key(48)
        generic = self.get_or_create_generic_product(app, secret=secret)

        exists = generic['seller_uuids']['reference']
        if exists:
            log.info('Reference product already exists: %s' % exists)
            return generic['resource_uri']

        uuid = get_uuid('reference-product')
        data = {
            'seller_product': generic['resource_uri'],
            'seller_reference': account.uri,
            'name': unicode(app.name),
            'uuid': uuid
        }
        log.info('Creating Reference product: '
                 'account {ac}, app {app}, uuid {uuid}'
                 .format(ac=account.pk, app=app.pk, uuid=uuid))
        created = self.client.products.post(data=data)
        return created['resource_uri']

    @account_check
    def terms_retrieve(self, account):
        res = self.client.terms(account.account_id).get()
        res['text'] = bleach.clean(res['reference']['text'])
        log.info('Retreiving Reference terms: %s' % account.pk)
        return res

    @account_check
    def terms_update(self, account):
        account.update(agreed_tos=True)
        data = self.client.sellers(account.account_id).get()['reference']
        data['agreement'] = datetime.now().strftime('%Y-%m-%d')
        data['seller'] = account.seller_uri
        log.info('Updating Reference terms: %s' % account.pk)
        return self.client.sellers(account.account_id).put(data)


ALL_PROVIDERS = {}
ALL_PROVIDERS_BY_ID = {}
for p in (Bango, Reference):
    ALL_PROVIDERS[p.name] = p
    ALL_PROVIDERS_BY_ID[p.provider] = p


def get_provider(name=None, id=None):
    """
    Get a provider implementation instance by name or id.
    """
    if id is not None:
        provider = ALL_PROVIDERS_BY_ID[id]()
    else:
        if name is None:
            # This returns the default provider so we can provide backwards
            # capability for API's that expect get_provider to return 'bango'.
            # TODO: This should raise an exception after we clean up Bango
            # code.
            name = settings.DEFAULT_PAYMENT_PROVIDER
        provider = ALL_PROVIDERS[name]()
    if provider.name not in settings.PAYMENT_PROVIDERS:
        raise ImproperlyConfigured(
            'The provider {p} is not one of the '
            'allowed PAYMENT_PROVIDERS.'.format(p=provider.name))
    return provider


def get_providers():
    return [ALL_PROVIDERS[name]() for name in settings.PAYMENT_PROVIDERS]
