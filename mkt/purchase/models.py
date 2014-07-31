import datetime

from django.conf import settings
from django.db import models
from django.utils import translation

import tower
from babel import Locale, numbers
from jingo import env
from jinja2.filters import do_dictsort
from tower import ugettext as _

import amo
from amo.fields import DecimalCharField
from amo.helpers import absolutify, urlparams
from amo.utils import get_locale_from_lang, send_mail, send_mail_jinja


class ContributionError(Exception):

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class Contribution(amo.models.ModelBase):
    addon = models.ForeignKey('webapps.Addon', blank=True, null=True)
    # For in-app purchases this links to the product.
    inapp_product = models.ForeignKey('inapp.InAppProduct',
                                      blank=True, null=True)
    amount = DecimalCharField(max_digits=9, decimal_places=2,
                              nullify_invalid=True, null=True)
    currency = models.CharField(max_length=3,
                                choices=do_dictsort(amo.PAYPAL_CURRENCIES),
                                default=amo.CURRENCY_DEFAULT)
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
    type = models.PositiveIntegerField(default=amo.CONTRIB_TYPE_DEFAULT,
                                       choices=do_dictsort(amo.CONTRIB_TYPES))
    price_tier = models.ForeignKey('prices.Price', blank=True, null=True,
                                   on_delete=models.PROTECT)
    # If this is a refund or a chargeback, which charge did it relate to.
    related = models.ForeignKey('self', blank=True, null=True,
                                on_delete=models.PROTECT)

    class Meta:
        db_table = 'stats_contributions'

    def __unicode__(self):
        return u'App {app}: in-app: {inapp}: {amount}'.format(
            app=self.addon, amount=self.amount, inapp=self.inapp_product)

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
        tower.activate(lang)
        return Locale(translation.to_locale(lang))

    def _mail(self, template, subject, context):
        template = env.get_template(template)
        body = template.render(context)
        send_mail(subject, body, settings.MARKETPLACE_EMAIL,
                  [self.user.email], fail_silently=True)

    def record_failed_refund(self, e, user):
        self.enqueue_refund(amo.REFUND_FAILED, user,
                            rejection_reason=str(e))
        self._switch_locale()
        self._mail('users/support/emails/refund-failed.txt',
                   # L10n: the addon name.
                   _(u'%s refund failed' % self.addon.name),
                   {'name': self.addon.name})
        send_mail_jinja(
            'Refund failed', 'purchase/email/refund-failed.txt',
            {'name': self.user.email,
             'error': str(e)},
            settings.MARKETPLACE_EMAIL,
            [str(self.addon.support_email)], fail_silently=True)

    def mail_approved(self):
        """The developer has approved a refund."""
        locale = self._switch_locale()
        amt = numbers.format_currency(abs(self.amount), self.currency,
                                      locale=locale)
        self._mail('users/support/emails/refund-approved.txt',
                   # L10n: the adddon name.
                   _(u'%s refund approved' % self.addon.name),
                   {'name': self.addon.name, 'amount': amt})

    def mail_declined(self):
        """The developer has declined a refund."""
        self._switch_locale()
        self._mail('users/support/emails/refund-declined.txt',
                   # L10n: the adddon name.
                   _(u'%s refund declined' % self.addon.name),
                   {'name': self.addon.name})

    def enqueue_refund(self, status, user, refund_reason=None,
                       rejection_reason=None):
        """Keep track of a contribution's refund status."""
        from mkt.prices.models import Refund
        refund, c = Refund.objects.safer_get_or_create(contribution=self,
                                                       user=user)
        refund.status = status

        # Determine which timestamps to update.
        timestamps = []
        if status in (amo.REFUND_PENDING, amo.REFUND_APPROVED_INSTANT,
                      amo.REFUND_FAILED):
            timestamps.append('requested')
        if status in (amo.REFUND_APPROVED, amo.REFUND_APPROVED_INSTANT):
            timestamps.append('approved')
        elif status == amo.REFUND_DECLINED:
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
            related=self, type=amo.CONTRIB_REFUND).order_by('-modified')

    def is_refunded(self):
        """
        If related has been set, then this transaction has been refunded or
        charged back. This is a bit expensive, so refrain from using on listing
        pages.
        """
        return (Contribution.objects.filter(related=self,
                                            type__in=[amo.CONTRIB_REFUND,
                                                      amo.CONTRIB_CHARGEBACK])
                                    .exists())
