import re

from django.core import exceptions
from django.db import models
from django.forms import fields

from tower import ugettext as _


class SeparatedValuesField(fields.Field):
    """
    Field that allows the given base field to accept multiple values using
    the given separator.

    E.g.::

        >>> field = SeparatedValuesField(forms.EmailField)
        >>> field.clean(u'a@b.com,,   \n,c@d.com')
        u'a@b.com, c@d.com'

    """

    def __init__(self, base_field, separator=None, *args, **kwargs):
        super(SeparatedValuesField, self).__init__(*args, **kwargs)
        self.base_field = base_field
        self.separator = separator or ','

    def clean(self, data):
        if not data:
            if self.required:
                raise exceptions.ValidationError(
                    _(u'Enter at least one value.'))
            else:
                return None

        value_list = filter(None, map(unicode.strip,
                                      data.split(self.separator)))

        self.value_list = []
        base_field = self.base_field()
        for value in value_list:
            if value:
                self.value_list.append(base_field.clean(value))

        return u', '.join(self.value_list)


class ColorField(models.CharField):
    """
    Model field that only accepts 7-character hexadecimal color
    representations, e.g. #FF0035.
    """
    description = _('Hexadecimal color')

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.get('max_length', 7)
        self.default_error_messages.update({
            'bad_hex': _('Must be a valid hex color code, e.g. #FF0035.'),
        })
        super(ColorField, self).__init__(*args, **kwargs)

    def validate(self, value, model_instance):
        if value and not re.match('^\#([0-9a-fA-F]{6})$', value):
            raise exceptions.ValidationError(self.error_messages['bad_hex'])
