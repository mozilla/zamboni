import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.utils import translation

import commonware.log
from babel import numbers
from cache_nuggets.lib import memoize_key
from jinja2.filters import do_dictsort
from tower import ugettext_lazy as _

import mkt
from lib.constants import ALL_CURRENCIES
from mkt.constants import apps
from mkt.constants.payments import (CARRIER_CHOICES, PAYMENT_METHOD_ALL,
                                    PAYMENT_METHOD_CHOICES, PROVIDER_CHOICES,
                                    PROVIDER_LOOKUP_INVERTED)
from mkt.constants.regions import RESTOFWORLD, REGIONS_CHOICES_ID_DICT as RID
from mkt.purchase.models import Contribution
from mkt.regions.utils import remove_accents
from mkt.site.decorators import use_master
from mkt.site.models import ManagerBase, ModelBase
from mkt.translations.utils import get_locale_from_lang
from mkt.users.models import UserProfile

log = commonware.log.getLogger('z.market')


def default_providers():
    """
    Returns a list of the default providers from the settings as the
    appropriate constants.
    """
    return [PROVIDER_LOOKUP_INVERTED[p] for p in settings.PAYMENT_PROVIDERS]


def price_locale(price, currency):
    lang = translation.get_language()
    locale = get_locale_from_lang(lang)
    return numbers.format_currency(price, currency, locale=locale)


def price_key(data):
    return ('carrier={carrier}|tier={tier}|region={region}|provider={provider}'
            .format(**data))


class PriceManager(ManagerBase):

    def get_queryset(self):
        qs = super(PriceManager, self).get_queryset()
        return qs.transform(Price.transformer)

    def active(self):
        return self.filter(active=True).order_by('price')


class Price(ModelBase):
    active = models.BooleanField(default=True, db_index=True)
    name = models.CharField(max_length=4)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # The payment methods availble for this tier.
    method = models.IntegerField(choices=PAYMENT_METHOD_CHOICES,
                                 default=PAYMENT_METHOD_ALL)

    objects = PriceManager()

    class Meta:
        db_table = 'prices'

    def tier_name(self):
        # L10n: %s is the name of the price tier, eg: 10.
        return _('Tier %s' % self.name)

    def tier_locale(self, currency='USD'):
        # Display the price of the tier in locale relevant way eg: $0.99
        return price_locale(self.price, currency)

    def __unicode__(self):
        # Display the price in unamiguous USD, eg: 0.99 USD
        return '{0} USD'.format(self.price)

    @staticmethod
    def transformer(prices):
        # There are a constrained number of price currencies, let's just
        # get them all.
        Price._currencies = dict(
            (price_key(model_to_dict(p)), p)
            for p in PriceCurrency.objects.filter(tier__active=True)
        )

    def get_price_currency(self, carrier=None, region=None, provider=None):
        """
        Returns the PriceCurrency object or none.

        :param optional carrier: an int for the carrier.
        :param optional region: an int for the region.
        :param optional provider: an int for the provider. Defaults to bango.
        """
        from mkt.developers.providers import ALL_PROVIDERS
        # Unless you specify a provider, we will give you the Bango tier.
        # This is probably ok for now, because Bango is the default fall back
        # however we might need to think about this for the long term.
        provider = (provider or
                    ALL_PROVIDERS[settings.DEFAULT_PAYMENT_PROVIDER].provider)
        if not hasattr(Price, '_currencies'):
            Price.transformer([])

        lookup = price_key({
            'tier': self.id, 'carrier': carrier,
            'provider': provider, 'region': region
        })

        try:
            price_currency = Price._currencies[lookup]
        except KeyError:
            return None

        return price_currency

    def get_price_data(self, carrier=None, regions=None, provider=None):
        """
        Returns a tuple of Decimal(price), currency.

        :param optional carrier: an int for the carrier.
        :param optional regions:
            a list of ints for the region to try in order, if not given
            default to RESTOFWORLD.
        :param optional provider: an int for the provider. Defaults to bango.
        """
        for region in regions:
            price_currency = self.get_price_currency(carrier=carrier,
                                                     region=region,
                                                     provider=provider)
            if price_currency:
                return price_currency.price, price_currency.currency

        return None, None

    def get_price(self, carrier=None, regions=None, provider=None):
        """Return the price as a decimal for the current locale."""
        return self.get_price_data(carrier=carrier, regions=regions,
                                   provider=provider)[0]

    def get_price_locale(self, carrier=None, regions=None, provider=None):
        """Return the price as a nicely localised string for the locale."""
        price, currency = self.get_price_data(carrier=carrier, regions=regions,
                                              provider=provider)
        if price is not None and currency is not None:
            return price_locale(price, currency)

    def prices(self, provider=None):
        """
        A list of dicts of all the currencies and prices for this tier.

        :param int provider: A provider, using the PAYMENT_* constant.
            If not provided it will use settings.PAYMENT_PROVIDERS,
        """
        providers = [provider] if provider else default_providers()
        return [model_to_dict(o) for o in
                self.pricecurrency_set.filter(provider__in=providers)]

    def regions_by_name(self, provider=None):
        """A list of price regions sorted by name.

        :param int provider: A provider, using the PAYMENT_* constant.
            If not provided it will use settings.PAYMENT_PROVIDERS,

        """

        prices = self.prices(provider=provider)

        regions = set()
        append_rest_of_world = False

        for price in prices:
            region = RID[price['region']]
            if price['paid'] is True and region != RESTOFWORLD:
                regions.add(region)
            if price['paid'] is True and region == RESTOFWORLD:
                append_rest_of_world = True

        if regions:
            # Sort by name based on normalized unicode name.
            regions = sorted(regions,
                             key=lambda r: remove_accents(unicode(r.name)))
            if append_rest_of_world:
                regions.append(RESTOFWORLD)

        return regions if regions else []

    def region_ids_by_name(self, provider=None):
        """A list of price region ids sorted by name.

        :param int provider: A provider, using the PAYMENT_* constant.
            If not provided it will use settings.PAYMENT_PROVIDERS,

        """
        return [region.id for region in
                self.regions_by_name(provider=provider)]

    def provider_regions(self):
        """A dict of provider regions keyed by provider id.

        Sorted by name (except for rest of world which is
        always last).

        """

        # Avoid circular import.
        from mkt.developers.providers import get_providers

        provider_regions = {}
        providers = get_providers()
        for prv in providers:
            provider_regions[prv.provider] = self.regions_by_name(
                provider=prv.provider)
        return provider_regions


class PriceCurrency(ModelBase):
    # The carrier for this currency.
    carrier = models.IntegerField(choices=CARRIER_CHOICES, blank=True,
                                  null=True)
    currency = models.CharField(max_length=10,
                                choices=do_dictsort(ALL_CURRENCIES))
    price = models.DecimalField(max_digits=10, decimal_places=2)

    # The payments provider for this tier.
    provider = models.IntegerField(choices=PROVIDER_CHOICES, blank=True,
                                   null=True)

    # The payment methods allowed for this tier.
    method = models.IntegerField(choices=PAYMENT_METHOD_CHOICES,
                                 default=PAYMENT_METHOD_ALL)

    # These are the regions as defined in mkt/constants/regions.
    region = models.IntegerField(default=1)  # Default to restofworld.
    tier = models.ForeignKey(Price)

    # If this should show up in the developer hub.
    dev = models.BooleanField(default=True)

    # If this can currently accept payments from mkt.users.
    paid = models.BooleanField(default=True)

    class Meta:
        db_table = 'price_currency'
        verbose_name = 'Price currencies'
        unique_together = ('tier', 'currency', 'carrier', 'region',
                           'provider')

    def __unicode__(self):
        return u'%s, %s: %s' % (self.tier, self.currency, self.price)


@receiver(models.signals.post_save, sender=PriceCurrency,
          dispatch_uid='save_price_currency')
@receiver(models.signals.post_delete, sender=PriceCurrency,
          dispatch_uid='delete_price_currency')
def update_price_currency(sender, instance, **kw):
    """
    Ensure that when PriceCurrencies are updated, all the apps that use them
    are re-indexed into ES so that the region information will be correct.
    """
    if kw.get('raw'):
        return

    try:
        ids = list(instance.tier.addonpremium_set
                           .values_list('addon_id', flat=True))
    except Price.DoesNotExist:
        return

    if ids:
        log.info('Indexing {0} add-ons due to PriceCurrency changes'
                 .format(len(ids)))

        # Circular import sad face.
        from mkt.webapps.tasks import index_webapps
        index_webapps.delay(ids)


class AddonPurchase(ModelBase):
    addon = models.ForeignKey('webapps.Webapp')
    type = models.PositiveIntegerField(default=mkt.CONTRIB_PURCHASE,
                                       choices=do_dictsort(mkt.CONTRIB_TYPES),
                                       db_index=True)
    user = models.ForeignKey(UserProfile)
    uuid = models.CharField(max_length=255, db_index=True, unique=True)

    class Meta:
        db_table = 'addon_purchase'
        unique_together = ('addon', 'user')

    def __unicode__(self):
        return u'%s: %s' % (self.addon, self.user)


@receiver(models.signals.post_save, sender=AddonPurchase)
def add_uuid(sender, **kw):
    if not kw.get('raw'):
        record = kw['instance']
        if not record.uuid:
            record.uuid = '{pk}-{u}'.format(pk=record.pk, u=str(uuid.uuid4()))
            record.save()


@use_master
@receiver(models.signals.post_save, sender=Contribution,
          dispatch_uid='create_addon_purchase')
def create_addon_purchase(sender, instance, **kw):
    """
    When the contribution table is updated with the data from PayPal,
    update the addon purchase table. Will figure out if we need to add to or
    delete from the AddonPurchase table.
    """
    if (kw.get('raw') or
        instance.type not in [mkt.CONTRIB_PURCHASE, mkt.CONTRIB_REFUND,
                              mkt.CONTRIB_CHARGEBACK]):
        # Filter the types we care about. Forget about the rest.
        return

    log.info('Processing addon purchase type: {t}, addon {a}, user {u}'
             .format(t=unicode(mkt.CONTRIB_TYPES[instance.type]),
                     a=instance.addon and instance.addon.pk,
                     u=instance.user and instance.user.pk))

    if instance.is_inapp_simulation():
        log.info('Simulated in-app product {i} for contribution {c}: '
                 'not adding a purchase record'.format(
                     i=instance.inapp_product,
                     c=instance))
        return

    if instance.type == mkt.CONTRIB_PURCHASE:
        log.debug('Creating addon purchase: addon %s, user %s'
                  % (instance.addon.pk, instance.user.pk))

        data = {'addon': instance.addon, 'user': instance.user}
        purchase, created = AddonPurchase.objects.safer_get_or_create(**data)
        purchase.update(type=mkt.CONTRIB_PURCHASE)
        from mkt.webapps.models import Installed  # Circular import
        # Ensure that devs have the correct installed object found
        # or created.
        #
        is_dev = instance.addon.has_author(
            instance.user, (mkt.AUTHOR_ROLE_OWNER, mkt.AUTHOR_ROLE_DEV))
        install_type = (apps.INSTALL_TYPE_DEVELOPER if is_dev
                        else apps.INSTALL_TYPE_USER)
        Installed.objects.safer_get_or_create(
            user=instance.user, addon=instance.addon,
            install_type=install_type)

    elif instance.type in [mkt.CONTRIB_REFUND, mkt.CONTRIB_CHARGEBACK]:
        purchases = AddonPurchase.objects.filter(addon=instance.addon,
                                                 user=instance.user)
        for p in purchases:
            log.debug('Changing addon purchase: %s, addon %s, user %s'
                      % (p.pk, instance.addon.pk, instance.user.pk))
            p.update(type=instance.type)

    cache.delete(memoize_key('users:purchase-ids', instance.user.pk))


class AddonPremium(ModelBase):
    """Additions to the Webapp model that only apply to Premium add-ons."""
    addon = models.OneToOneField('webapps.Webapp')
    price = models.ForeignKey(Price, blank=True, null=True)

    class Meta:
        db_table = 'addons_premium'

    def __unicode__(self):
        return u'Premium %s: %s' % (self.addon, self.price)

    def is_complete(self):
        return bool(self.addon and self.price and self.addon.support_email)


class RefundManager(ManagerBase):

    def by_addon(self, addon):
        return self.filter(contribution__addon=addon)

    def pending(self, addon=None):
        return self.by_addon(addon).filter(status=mkt.REFUND_PENDING)

    def approved(self, addon):
        return self.by_addon(addon).filter(status=mkt.REFUND_APPROVED)

    def instant(self, addon):
        return self.by_addon(addon).filter(status=mkt.REFUND_APPROVED_INSTANT)

    def declined(self, addon):
        return self.by_addon(addon).filter(status=mkt.REFUND_DECLINED)

    def failed(self, addon):
        return self.by_addon(addon).filter(status=mkt.REFUND_FAILED)


class Refund(ModelBase):
    # This refers to the original object with `type=mkt.CONTRIB_PURCHASE`.
    contribution = models.OneToOneField(Contribution)

    # Pending => 0
    # Approved => 1
    # Instantly Approved => 2
    # Declined => 3
    # Failed => 4
    status = models.PositiveIntegerField(
        default=mkt.REFUND_PENDING, choices=do_dictsort(mkt.REFUND_STATUSES),
        db_index=True)

    refund_reason = models.TextField(default='', blank=True)
    rejection_reason = models.TextField(default='', blank=True)

    # Date `created` should always be date `requested` for pending refunds,
    # but let's just stay on the safe side. We might change our minds.
    requested = models.DateTimeField(null=True, db_index=True)
    approved = models.DateTimeField(null=True, db_index=True)
    declined = models.DateTimeField(null=True, db_index=True)
    user = models.ForeignKey('users.UserProfile')

    objects = RefundManager()

    class Meta:
        db_table = 'refunds'

    def __unicode__(self):
        return u'%s (%s)' % (self.contribution, self.get_status_display())


class AddonPaymentData(ModelBase):
    # Store information about the app. This can be entered manually
    # or got from PayPal. At the moment, I'm just capturing absolutely
    # everything from PayPal and that's what these fields are.
    # Easier to do this and clean out later.
    # See: http://bit.ly/xy5BTs and http://bit.ly/yRYbRx
    #
    # I've no idea what the biggest lengths of these are, so making
    # up some aribtrary lengths.
    addon = models.OneToOneField('webapps.Webapp', related_name='payment_data')
    # Basic.
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    business_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=64)
    payerID = models.CharField(max_length=255, blank=True)
    # Advanced.
    address_one = models.CharField(max_length=255)
    address_two = models.CharField(max_length=255, blank=True)
    post_code = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=128, blank=True)
    state = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = 'addon_payment_data'

    @classmethod
    def address_fields(cls):
        return [field.name for field in cls._meta.fields
                if isinstance(field, (models.CharField, models.EmailField))]

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.addon)
