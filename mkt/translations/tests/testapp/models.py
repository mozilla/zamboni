from django.db import models

from mkt.site.models import TransformQuerySet
from mkt.translations import transformer
from mkt.translations.fields import (LinkifiedField, PurifiedField,
                                     save_signal, TranslatedField)


class ManagerWithTranslations(models.Manager):
    def get_queryset(self):
        qs = TransformQuerySet(self.model)
        if hasattr(self.model._meta, 'translated_fields'):
            qs = qs.transform(transformer.get_trans)
        return qs


class TranslatedModel(models.Model):
    name = TranslatedField()
    description = TranslatedField()
    default_locale = models.CharField(max_length=10)
    no_locale = TranslatedField(require_locale=False)

    objects = ManagerWithTranslations()

models.signals.pre_save.connect(save_signal, sender=TranslatedModel,
                                dispatch_uid='testapp_translatedmodel')


class UntranslatedModel(models.Model):
    """Make sure nothing is broken when a model doesn't have translations."""
    number = models.IntegerField()

    objects = ManagerWithTranslations()


class FancyModel(models.Model):
    """Mix it up with purified and linkified fields."""
    purified = PurifiedField()
    linkified = LinkifiedField()

    objects = ManagerWithTranslations()


models.signals.pre_save.connect(save_signal, sender=FancyModel,
                                dispatch_uid='testapp_fancymodel')
