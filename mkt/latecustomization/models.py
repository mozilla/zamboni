from django.db import models

import mkt
import mkt.carriers
import mkt.regions
from mkt.site.models import ModelBase
from mkt.extensions.models import Extension
from mkt.webapps.models import Webapp


class LateCustomizationItem(ModelBase):
    """
    An app or addon that can be automatically loaded as part of device
    first-time experience.
    """
    app = models.ForeignKey(Webapp, null=True, blank=True)
    extension = models.ForeignKey(Extension, null=True, blank=True)
    region = models.PositiveIntegerField(
        choices=mkt.regions.REGIONS_CHOICES_ID)
    carrier = models.IntegerField(choices=mkt.carriers.CARRIER_CHOICES)

    class Meta:
        db_table = 'late_customization_item'
        index_together = (('region', 'carrier'),)
