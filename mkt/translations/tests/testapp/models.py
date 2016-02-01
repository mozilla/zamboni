from django.db import models

from mkt.site.models import ModelBase, TransformQuerySet
from mkt.translations import transformer
from mkt.translations.fields import (LinkifiedField, PurifiedField,
                                     TranslatedField)


class ManagerWithTranslations(models.Manager):
    def get_queryset(self):
        qs = TransformQuerySet(self.model)
        if hasattr(self.model._meta, 'translated_fields'):
            qs = qs.transform(transformer.get_trans)
        return qs


class TranslatedModel(ModelBase):
    name = TranslatedField()
    description = TranslatedField()
    default_locale = models.CharField(max_length=10)
    no_locale = TranslatedField(require_locale=False)

    objects = ManagerWithTranslations()


class UntranslatedModel(ModelBase):
    """Make sure nothing is broken when a model doesn't have translations."""
    number = models.IntegerField()

    objects = ManagerWithTranslations()


class FancyModel(ModelBase):
    """Mix it up with purified and linkified fields."""
    purified = PurifiedField()
    linkified = LinkifiedField()

    objects = ManagerWithTranslations()
