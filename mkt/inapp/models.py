from django.db import models

from amo.models import ModelBase
from mkt.prices.models import Price
from mkt.translations.fields import save_signal, TranslatedField


class InAppProduct(ModelBase):
    """
    An item which is purchaseable from within a marketplace app.
    """
    webapp = models.ForeignKey('webapps.WebApp', null=True, blank=True)
    price = models.ForeignKey(Price)
    name = TranslatedField(require_locale=False)
    logo_url = models.URLField(max_length=1024, null=True, blank=True)
    # The JSON value for the simulate parameter of a JWT.
    # Example: {"result": "postback"}. This will be NULL for no simulation.
    simulate = models.CharField(max_length=100, null=True, blank=True)
    # When True, this is a stub product created internally.
    stub = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'inapp_products'

    def __unicode__(self):
        return u'<{cls} {id}: {app}: {name}>'.format(
            app=self.webapp and self.webapp.name,
            name=self.name, id=self.pk, cls=self.__class__.__name__)

    @property
    def icon_url(self):
        return self.logo_url or (self.webapp and self.webapp.get_icon_url(64))


models.signals.pre_save.connect(save_signal, sender=InAppProduct,
                                dispatch_uid='inapp_products_translations')
