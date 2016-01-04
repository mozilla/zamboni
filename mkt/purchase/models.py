import datetime

from django.conf import settings
from django.db import models
from django.utils import translation


from babel import Locale, numbers
from mkt.site.utils import env
from jingo.helpers import urlparams
from jinja2.filters import do_dictsort

import mkt
from mkt.site.helpers import absolutify
from mkt.site.mail import send_mail
from mkt.site.models import ModelBase
from mkt.translations.utils import get_locale_from_lang


class ContributionError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class Contribution(ModelBase):
    addon = models.ForeignKey('webapps.Webapp', blank=True, null=True)
    # For in-app purchases this links to the product.
    inapp_product = models.ForeignKey('inapp.InAppProduct',
                                      blank=True, null=True)
    amount = models.DecimalField(max_digits=9, decimal_places=2, blank=True,
                                 null=True)
    currency = models.CharField(max_length=3,
                                choices=do_dictsort(mkt.PAYPAL_CURRENCIES),
                                default=mkt.CURRENCY_DEFAULT)
    source = models.CharField(max_length=255, null=True)
    source_locale = models.CharField(max_length=10, null=True)
    # This is the external id that you can communicate to the world.
    uuid = models.CharField(max_length=255, null=True, db_index=True)
    comment = models.CharField(max_length=255)
    # This is the internal transaction id between us and a provider,
    # for example paypal or solitude.
    transaction_id = models.CharField(max_length=255, null=True, db_index=True)
    paykey = models.CharField(max_length=255, null=True)

    # Marketplace specific.
    # TODO(andym): figure out what to do when we delete the user.
    user = models.ForeignKey('users.UserProfile', blank=True, null=True)
    type = models.PositiveIntegerField(default=mkt.CONTRIB_TYPE_DEFAULT,
                                       choices=do_dictsort(mkt.CONTRIB_TYPES),
                                       db_index=True)
    price_tier = models.ForeignKey('prices.Price', blank=True, null=True,
                                   on_delete=models.PROTECT)
    # If this is a refund or a chargeback, which charge did it relate to.
    related = models.ForeignKey('self', blank=True, null=True,
                                on_delete=models.PROTECT)

    class Meta:
        db_table = 'stats_contributions'

    def __unicode__(self):
        return (u'<{cls} {pk}; app: {app}; in-app: {inapp}; amount: {amount}>'
                .format(app=self.addon, amount=self.amount, pk=self.pk,
                        inapp=self.inapp_product, cls=self.__class__.__name__))

    @property
    def date(self):
        try:
            return datetime.date(self.created.year,
                                 self.created.month, self.created.day)
        except AttributeError:
            # created may be None
            return None

    def _switch_locale(self):
        if self.source_locale:
            lang = self.source_locale
        else:
            lang = self.addon.default_locale
        translation.activate(lang)
        return Locale(translation.to_locale(lang))

    def _mail(self, template, subject, context):
        template = env.get_template(template)
        body = template.render(context)
        send_mail(subject, body, settings.MARKETPLACE_EMAIL,
                  [self.user.email], fail_silently=True)

    def is_inapp_simulation(self):
        """True if this purchase is for a simulated in-app product."""
        return self.inapp_product and self.inapp_product.simulate

    def enqueue_refund(self, status, user, refund_reason=None,
                       rejection_reason=None):
        """Keep track of a contribution's refund status."""
        from mkt.prices.models import Refund
        refund, c = Refund.objects.safer_get_or_create(contribution=self,
                                                       user=user)
        refund.status = status

        # Determine which timestamps to update.
        timestamps = []
        if status in (mkt.REFUND_PENDING, mkt.REFUND_APPROVED_INSTANT,
                      mkt.REFUND_FAILED):
            timestamps.append('requested')
        if status in (mkt.REFUND_APPROVED, mkt.REFUND_APPROVED_INSTANT):
            timestamps.append('approved')
        elif status == mkt.REFUND_DECLINED:
            timestamps.append('declined')
        for ts in timestamps:
            setattr(refund, ts, datetime.datetime.now())

        if refund_reason:
            refund.refund_reason = refund_reason
        if rejection_reason:
            refund.rejection_reason = rejection_reason
        refund.save()
        return refund

    def get_amount_locale(self, locale=None):
        """Localise the amount paid into the current locale."""
        if not locale:
            lang = translation.get_language()
            locale = get_locale_from_lang(lang)
        return numbers.format_currency(self.amount or 0,
                                       self.currency or 'USD',
                                       locale=locale)

    def get_refund_url(self):
        return urlparams(self.addon.get_dev_url('issue_refund'),
                         transaction_id=self.transaction_id)

    def get_absolute_refund_url(self):
        return absolutify(self.get_refund_url())

    def get_refund_contribs(self):
        """Get related set of refund contributions."""
        return Contribution.objects.filter(
            related=self, type=mkt.CONTRIB_REFUND).order_by('-modified')

    def is_refunded(self):
        """
        If related has been set, then this transaction has been refunded or
        charged back. This is a bit expensive, so refrain from using on listing
        pages.
        """
        return (Contribution.objects.filter(related=self,
                                            type__in=[mkt.CONTRIB_REFUND,
                                                      mkt.CONTRIB_CHARGEBACK])
                                    .exists())
