from django import forms

import commonware.log
from tower import ugettext as _

log = commonware.log.getLogger('z.mkt.site.forms')

APP_PUBLIC_CHOICES = (
    (0, _('As soon as it is approved.')),
    (1, _('Not until I manually make it public.')),
)


class WebappChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name
