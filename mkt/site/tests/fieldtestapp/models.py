from django.db import models

from mkt.site.fields import DecimalCharField


class DecimalCharFieldModel(models.Model):
    strict = DecimalCharField(max_digits=10, decimal_places=2)
    loose = DecimalCharField(max_digits=10, decimal_places=2,
                             nullify_invalid=True, null=True)
