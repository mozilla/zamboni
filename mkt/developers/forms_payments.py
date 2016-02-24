from mkt.constants import FREE_PLATFORMS
from django.core.exceptions import ValidationError

import commonware
import happyforms
from django.utils.translation import ugettext as _

import mkt

from mkt.api.forms import SluggableModelChoiceField
from mkt.developers.models import AddonPaymentAccount
from mkt.prices.models import AddonPremium
from mkt.submit.forms import DeviceTypeForm
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('z.devhub')


def _restore_app_status(app, save=True):
    """
    Restore an incomplete app to its former status. The app will be marked
    as its previous status or PENDING if it was never reviewed.
    """

    log.info('Changing app from incomplete to previous status: %d' % app.pk)
    app.status = (app.highest_status if
                  app.highest_status != mkt.STATUS_NULL else
                  mkt.STATUS_PENDING)
    if save:
        app.save()


class PremiumForm(DeviceTypeForm, happyforms.Form):
    """
    The premium details for an addon, which is unfortunately
    distributed across a few models.
    """

    def __init__(self, *args, **kw):
        self.request = kw.pop('request')
        self.addon = kw.pop('addon')
        self.user = kw.pop('user')

        kw['initial'] = {
            'allow_inapp': self.addon.premium_type in mkt.ADDON_INAPPS
        }

        if self.addon.premium_type == mkt.ADDON_FREE_INAPP:
            kw['initial']['price'] = 'free'
        elif self.addon.premium and self.addon.premium.price:
            # If the app has a premium object, set the initial price.
            kw['initial']['price'] = self.addon.premium.price.pk

        super(PremiumForm, self).__init__(*args, **kw)

        self.fields['free_platforms'].choices = FREE_PLATFORMS()

        # Get the list of supported devices and put them in the data.
        self.device_data = {}
        supported_devices = [mkt.REVERSE_DEVICE_LOOKUP[dev.id] for dev in
                             self.addon.device_types]
        self.initial.setdefault('free_platforms', [])
        self.initial.setdefault('paid_platforms', [])

        for platform in set(x[0].split('-', 1)[1] for x in FREE_PLATFORMS()):
            supported = platform in supported_devices
            self.device_data['free-%s' % platform] = supported

            if supported:
                self.initial['free_platforms'].append('free-%s' % platform)

    def is_paid(self):
        is_paid = (self.addon.premium_type in mkt.ADDON_PREMIUMS or
                   self.addon.premium_type == mkt.ADDON_FREE_INAPP)
        return is_paid

    def clean(self):
        return self.cleaned_data

    def save(self):
        upsell = self.addon.upsold

        # is_paid is true for both premium apps and free apps with
        # in-app payments.
        is_paid = self.is_paid()

        if is_paid:
            # If the app is paid and we're making it free, remove it as an
            # upsell (if an upsell exists).
            upsell = self.addon.upsold
            if upsell:
                log.debug('[1@%s] Removing upsell; switching to free' %
                          self.addon.pk)
                upsell.delete()

            log.debug('[1@%s] Removing app payment account' % self.addon.pk)
            AddonPaymentAccount.objects.filter(addon=self.addon).delete()

            log.debug('[1@%s] Setting app premium_type to FREE' %
                      self.addon.pk)
            self.addon.premium_type = mkt.ADDON_FREE

            # Remove addonpremium
            try:
                log.debug('[1@%s] Removing addon premium' % self.addon.pk)
                self.addon.addonpremium.delete()
            except AddonPremium.DoesNotExist:
                pass

            if (self.addon.has_incomplete_status() and
                    self.addon.is_fully_complete()):
                _restore_app_status(self.addon, save=False)

            is_paid = False

        else:
            # Save the device compatibility information when we're not
            # toggling.
            super(PremiumForm, self).save(self.addon, is_paid)

        log.info('Saving app payment changes for addon %s.' % self.addon.pk)
        self.addon.save()


class PaymentCheckForm(happyforms.Form):
    app = SluggableModelChoiceField(
        queryset=Webapp.objects.filter(
            premium_type__in=mkt.ADDON_HAS_PAYMENTS),
        sluggable_to_field_name='app_slug')

    def clean_app(self):
        app = self.cleaned_data['app']
        if not app.has_payment_account():
            raise ValidationError(_('No payment account set up for that app'))

        return app
