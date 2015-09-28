from django.conf import settings
from django.core import validators
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils.encoding import smart_text
from django.utils.translation import ugettext_lazy as _

from rest_framework import fields, serializers

from mkt.submit.helpers import string_to_translatedfield_value
from mkt.translations.utils import to_language


class MultiSlugChoiceField(fields.Field):
    """
    Like SlugChoiceField but accepts a list of values rather a single one.
    """
    type_name = 'MultiSlugChoiceField'
    type_label = 'multiple choice'
    default_error_messages = {
        'invalid_choice': _('Select a valid choice. %(value)s is not one of '
                            'the available choices.'),
    }

    def __init__(self, choices_dict=None, *args, **kwargs):
        super(MultiSlugChoiceField, self).__init__(*args, **kwargs)
        # Create a choice dynamically to allow None, slugs and ids. Also store
        # choices_dict and ids_choices_dict to re-use them later in to_native()
        # and from_native().
        self.choices_dict = choices_dict
        slugs_choices = self.choices_dict.items()
        ids_choices = [(v.id, v) for v in self.choices_dict.values()]
        self.ids_choices_dict = dict(ids_choices)
        self.choices = slugs_choices + ids_choices
        if not self.required:
            self.choices = BLANK_CHOICE_DASH + self.choices

    def valid_value(self, value):
        """
        Check to see if the provided value is a valid choice.
        """
        for k, v in self.choices:
            if isinstance(v, (list, tuple)):
                # This is an optgroup, so look inside the group for options
                for k2, v2 in v:
                    if value == smart_text(k2):
                        return True
            else:
                if value == smart_text(k) or value == k:
                    return True
        return False

    def to_internal_value(self, value):
        if value in validators.EMPTY_VALUES:
            return None
        for v in value:
            if not self.valid_value(v):
                raise ValidationError(self.error_messages['invalid_choice'] % {
                    'value': v})
        return super(MultiSlugChoiceField, self).to_internal_value(value)


class TranslationSerializerField(fields.Field):
    """
    Django-rest-framework custom serializer field for our TranslatedFields.

    - When deserializing, in `from_native`, it accepts both a string or a
      dictionary. If a string is given, it'll be considered to be in the
      default language.

    - When serializing, its behavior depends on the parent's serializer
      context:

      If a request was included, and its method is 'GET', and a 'lang'
      parameter was passed, then only returns one translation (letting the
      TranslatedField figure out automatically which language to use).

      Else, just returns a dict with all translations for the given
      `field_name` on `obj`, with languages as the keys.
    """
    default_error_messages = {
        'min_length': _('The field must have a length of at least {num} '
                        'characters.'),
        'unknown_locale': _('The language code {lang_code} is invalid.')
    }

    def __init__(self, *args, **kwargs):
        self.min_length = kwargs.pop('min_length', None)
        super(TranslationSerializerField, self).__init__(*args, **kwargs)
        self.requested_language = None

    def fetch_all_translations(self, obj, source, field):
        translations = field.__class__.objects.filter(
            id=field.id, localized_string__isnull=False)
        return dict((to_language(trans.locale), unicode(trans))
                    for trans in translations) if translations else None

    def fetch_single_translation(self, obj, source, field, requested_language):
        return unicode(field) if field else None

    def get_attribute(self, obj, requested_language=None):
        source = self.source or self.field_name
        field = fields.get_attribute(obj, source.split('.'))
        if not field:
            return None
        request = self.context.get('request', None)
        if requested_language is None:
            if request and request.method == 'GET' and 'lang' in request.GET:
                requested_language = request.GET['lang']
        if requested_language:
            return self.fetch_single_translation(obj, source, field,
                                                 requested_language)
        else:
            return self.fetch_all_translations(obj, source, field)

    def to_representation(self, val):
        return val

    def to_internal_value(self, data):
        if isinstance(data, basestring):
            self.validate(data)
            return data.strip()
        elif isinstance(data, dict):
            self.validate(data)
            for key, value in data.items():
                data[key] = value and value.strip()
            return data
        return unicode(data)

    def validate(self, value):
        value_too_short = True

        if isinstance(value, basestring):
            if len(value.strip()) >= self.min_length:
                value_too_short = False
        else:
            for locale, string in value.items():
                if locale.lower() not in settings.LANGUAGES:
                    raise ValidationError(
                        self.error_messages['unknown_locale'].format(
                            lang_code=repr(locale)))
                if string and (len(string.strip()) >= self.min_length):
                    value_too_short = False
                    break

        if self.min_length and value_too_short:
            raise ValidationError(
                self.error_messages['min_length'].format(num=self.min_length))


class ESTranslationSerializerField(TranslationSerializerField):
    """
    Like TranslationSerializerField, but fetching the data from a dictionary
    built from ES data that we previously attached on the object.
    """
    suffix = '_translations'
    _source = None

    def get_source(self):
        if self._source is None:
            return None
        return self._source + self.suffix

    def set_source(self, val):
        self._source = val

    source = property(get_source, set_source)

    @classmethod
    def attach_translations(cls, obj, data, source_name, target_name=None):
        """
        Look for the translation of `source_name` in `data` and create a dict
        with all translations for this field (which will look like
        {'en-US': 'mytranslation'}) and attach it to a property on `obj`.
        The property name is built with `target_name` and `cls.suffix`. If
        `target_name` is None, `source_name` is used instead.

        The suffix is necessary for two reasons:
        1) The translations app won't let us set the dict on the real field
           without making db queries
        2) This also exactly matches how we store translations in ES, so we can
           directly fetch the translations in the data passed to this method.
        """
        if target_name is None:
            target_name = source_name
        target_key = '%s%s' % (target_name, cls.suffix)
        source_key = '%s%s' % (source_name, cls.suffix)
        setattr(obj, target_key, dict((v.get('lang', ''), v.get('string', ''))
                                      for v in data.get(source_key, {}) or {}))

    def fetch_all_translations(self, obj, source, field):
        return field or None

    def fetch_single_translation(self, obj, source, field, requested_language):
        translations = self.fetch_all_translations(obj, source, field) or {}
        return (translations.get(requested_language) or
                translations.get(getattr(obj, 'default_locale', None)) or
                translations.get(getattr(obj, 'default_language', None)) or
                translations.get(settings.LANGUAGE_CODE) or None)


class GuessLanguageTranslationField(TranslationSerializerField):
    def to_internal_value(self, obj):
        return string_to_translatedfield_value(obj)


class SplitField(fields.Field):
    """
    A field composed of two separate fields: one used for input, and another
    used for output. Most commonly used to accept a primary key for input and
    use a full serializer for output.

    Example usage:
    app = SplitField(PrimaryKeyRelatedField(), AppSerializer())
    """
    label = None

    def __init__(self, input, output, **kwargs):
        self.input = input
        self.output = output
        kwargs['required'] = input.required
        fields.Field.__init__(self, source=input.source, **kwargs)

    def bind(self, field_name, parent):
        fields.Field.bind(self, field_name, parent)
        self.input.bind(field_name, parent)
        self.output.bind(field_name, parent)

    def get_read_only(self):
        return self._read_only

    def set_read_only(self, val):
        self._read_only = val
        self.input.read_only = val
        self.output.read_only = val

    read_only = property(get_read_only, set_read_only)

    def get_value(self, data):
        return self.input.get_value(data)

    def to_internal_value(self, value):
        return self.input.to_internal_value(value)

    def get_attribute(self, obj):
        return self.output.get_attribute(obj)

    def to_representation(self, value):
        return self.output.to_representation(value)


class SlugOrPrimaryKeyRelatedField(serializers.RelatedField):
    """
    Combines SlugRelatedField and PrimaryKeyRelatedField. Takes a
    `render_as` argument (either "pk" or "slug") to indicate how to
    serialize.
    """
    read_only = False

    def __init__(self, *args, **kwargs):
        self.render_as = kwargs.pop('render_as', 'pk')
        if self.render_as not in ['pk', 'slug']:
            raise ValueError("'render_as' must be one of 'pk' or 'slug', "
                             "not %r" % (self.render_as,))
        self.slug_field = kwargs.pop('slug_field', 'slug')
        super(SlugOrPrimaryKeyRelatedField, self).__init__(
            *args, **kwargs)

    def to_representation(self, obj):
        if self.render_as == 'slug':
            return getattr(obj, self.slug_field)
        else:
            return obj.pk

    def to_internal_value(self, data):
        if self.queryset is None:
            raise Exception('Writable related fields must include a '
                            '`queryset` argument')

        try:
            return self.queryset.get(pk=data)
        except:
            try:
                return self.queryset.get(**{self.slug_field: data})
            except ObjectDoesNotExist:
                msg = (_('Invalid pk or slug "%s" - object does not exist') %
                       smart_text(data))
                raise ValidationError(msg)


class ReverseChoiceField(serializers.ChoiceField):
    """
    A ChoiceField that serializes and de-serializes using the human-readable
    version of the `choices_dict` that is passed.

    The values in the choices_dict passed must be unique.
    """
    def __init__(self, *args, **kwargs):
        self.choices_dict = kwargs.pop('choices_dict')
        kwargs['choices'] = self.choices_dict.items()
        self.reversed_choices_dict = dict((v, k) for k, v
                                          in self.choices_dict.items())
        return super(ReverseChoiceField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        """
        Convert "actual" value to "human-readable" when serializing.
        """
        value = self.choices_dict.get(value, None)
        return super(ReverseChoiceField, self).to_representation(value)

    def to_internal_value(self, value):
        """
        Convert "human-readable" value to "actual" when de-serializing.
        """
        value = self.reversed_choices_dict.get(value, None)
        return super(ReverseChoiceField, self).to_internal_value(value)


class SlugChoiceField(serializers.ChoiceField):
    """
    Companion to SlugChoiceFilter, this field accepts an id or a slug when
    de-serializing, but always return a slug for serializing.

    Like SlugChoiceFilter, it needs to be initialized with a `choices_dict`
    mapping the slugs to objects with id and slug properties. This will be used
    to overwrite the choices in the underlying code.

    The values in the choices_dict passed must be unique.
    """
    def __init__(self, *args, **kwargs):
        # Create a choice dynamically to allow None, slugs and ids. Also store
        # choices_dict and ids_choices_dict to re-use them later in to_native()
        # and from_native().
        self.choices_dict = kwargs.pop('choices_dict')
        slugs_choices = self.choices_dict.items()
        ids_choices = [(v.id, v) for v in self.choices_dict.values()]
        self.ids_choices_dict = dict(ids_choices)
        kwargs['choices'] = slugs_choices + ids_choices
        return super(SlugChoiceField, self).__init__(*args, **kwargs)

    def metadata(self):
        """Return metadata about the choices. It's customized to return the
        name of each choice, because in that class, choices values are objects,
        not strings directly. This makes it possible to serialize the metadata
        without errors, which is necessary to answer OPTIONS (bug 984899)"""
        data = super(SlugChoiceField, self).metadata()
        data['choices'] = [{'value': v,
                            'display_name': unicode(getattr(n, 'name', n))}
                           for v, n in self.choices]
        return data

    def to_representation(self, value):
        if value is not fields.empty:
            choice = self.ids_choices_dict.get(value, None)
            if choice is not None:
                value = choice.slug
        return super(SlugChoiceField, self).to_representation(value)

    def to_internal_value(self, value):
        if isinstance(value, basestring):
            choice = self.choices_dict.get(value, None)
            if choice is not None:
                value = choice.id
        return super(SlugChoiceField, self).to_internal_value(value)


class UnicodeChoiceField(serializers.ChoiceField):
    """
    A ChoiceField that forces its choice values to be rendered with unicode()
    when displaying metadata (information about available choices, for OPTIONS)
    """
    def metadata(self):
        data = super(UnicodeChoiceField, self).metadata()
        data['choices'] = [{'display_name': k, 'value': unicode(v)}
                           for k, v in self.choices]
        return data


class SlugModelChoiceField(serializers.PrimaryKeyRelatedField):
    def get_attribute(self, obj):
        value = getattr(obj, self.source)
        return getattr(value, 'slug', None)

    def to_internal_value(self, data):
        if isinstance(data, basestring):
            try:
                data = self.queryset.only('pk').get(slug=data).pk
            except ObjectDoesNotExist:
                msg = self.error_messages['does_not_exist'] % smart_text(data)
                raise serializers.ValidationError(msg)
        return super(SlugModelChoiceField, self).to_internal_value(data)


class LargeTextField(serializers.HyperlinkedRelatedField):
    """
    Accepts a value for a field when unserializing, but serializes as
    a link to a separate resource. Used for text too long for common
    inclusion in a resource.
    """

    def get_attribute(self, obj):
        return obj

    def to_internal_value(self, value):
        return value


class SemiSerializerMethodField(serializers.SerializerMethodField):
    """
    Used for fields serialized with a method on the serializer but who
    need to handle unserialization manually.
    """
    def __init__(self, method_name=None, **kwargs):
        # Intentionally skipping SerializerMethodField.__init__.
        self.method_name = method_name
        serializers.Field.__init__(self, **kwargs)

    def to_internal_value(self, data):
        return data


class IntegerRangeField(models.IntegerField):
    """
    Subclass of IntegerField that adds two params:

    - `min_value` - minimum value of the field
    - `max_value` - maximum value of the field

    Usage:
    likert_field = models.IntegerRangeField(min_value=1, max_value=5)
    """
    def __init__(self, verbose_name=None, name=None, min_value=None,
                 max_value=None, **kwargs):
        self.min_value = min_value
        self.max_value = max_value
        models.IntegerField.__init__(self, verbose_name, name, **kwargs)

    def to_python(self, value):
        if self.min_value is not None and value < self.min_value:
            raise ValidationError('%s is less than the min value of %s' % (
                                  value, self.min_value))
        if self.max_value is not None and value > self.max_value:
            raise ValidationError('%s is more than the max value of %s' % (
                                  value, self.max_value))
        return super(IntegerRangeField, self).to_python(value)
