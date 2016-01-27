from cStringIO import StringIO

from django import forms
from django.conf import settings
from django.utils.translation import trans_real as translation

import commonware
import requests
from jinja2.filters import do_dictsort
from PIL import Image
from rest_framework import serializers
from rest_framework.serializers import ValidationError
from django.utils.translation import ugettext as _

from mkt.prices.models import Price
from mkt.api.fields import TranslationSerializerField
from mkt.api.forms import SchemeURLValidator as URLValidator
from mkt.inapp.models import InAppProduct


log = commonware.log.getLogger('z.inapp')


class NameField(TranslationSerializerField):

    def get_attribute(self, obj):
        # TODO: maybe remove this when the API response is fixed in
        # bug 1070125
        return super(NameField, self).get_attribute(
            obj, requested_language=obj.default_locale)


class InAppProductSerializer(serializers.ModelSerializer):
    _locales = [(translation.to_locale(k).replace('_', '-').lower(), v)
                for k, v in do_dictsort(settings.LANGUAGES)]

    app = serializers.SlugRelatedField(read_only=True, slug_field='app_slug',
                                       source='webapp')
    guid = serializers.CharField(read_only=True)
    include_inactive = serializers.BooleanField(read_only=True)
    logo_url = serializers.CharField(
        validators=[URLValidator(schemes=['http', 'https'])],
        required=False)
    name = NameField()
    default_locale = serializers.ChoiceField(choices=_locales)
    price_id = serializers.PrimaryKeyRelatedField(source='price',
                                                  queryset=Price.objects)

    class Meta:
        model = InAppProduct
        fields = ['active', 'guid', 'app', 'price_id', 'name',
                  'default_locale', 'logo_url', 'include_inactive']

    def validate(self, attrs):
        default_name = attrs['name'].get(attrs['default_locale'], None)
        if ((attrs['default_locale'] not in attrs['name']) or
                not default_name):
            raise ValidationError(
                'no localization for default_locale {d} in "name"'
                .format(d=repr(attrs['default_locale'])))
        return attrs

    def validate_logo_url(self, logo_url):

        # This message is shown for all image errors even though it may
        # not be correct. This is to prevent leaking info that could
        # lead to port scanning, DOS'ing or other vulnerabilities.
        msg = _('Product logo must be a 64x64 image. '
                'Check that the URL is correct.')
        tmp_dest = StringIO()
        try:
            res = requests.get(
                logo_url, timeout=3,
                headers={'User-Agent': settings.MARKETPLACE_USER_AGENT})
            res.raise_for_status()
            payload = 0
            read_size = 100000
            for chunk in res.iter_content(read_size):
                payload += len(chunk)
                if payload > settings.MAX_INAPP_IMAGE_SIZE:
                    log.info('clean_logo_url: payload exceeded allowed '
                             'size: {url}: '.format(url=logo_url))
                    raise ValidationError(msg)
                tmp_dest.write(chunk)
        except ValidationError:
            raise
        except Exception, exc:
            log.info('clean_logo_url: exception fetching {url}: '
                     '{exc.__class__.__name__}: {exc}'
                     .format(url=logo_url, exc=exc))
            raise ValidationError(msg)

        tmp_dest.seek(0)
        try:
            img = Image.open(tmp_dest)
            img.verify()
        except Exception, exc:
            log.info('clean_logo_url: Error loading/verifying {url}: '
                     '{exc.__class__.__name__}: {exc}'
                     .format(url=logo_url, exc=exc))
            raise ValidationError(msg)
        if img.size != (settings.REQUIRED_INAPP_IMAGE_SIZE,
                        settings.REQUIRED_INAPP_IMAGE_SIZE):
            log.info('clean_logo_url: not a valid size: {url}; '
                     'width={size[0]}; height={size[1]}'
                     .format(url=logo_url, size=img.size))
            raise ValidationError(msg)

        return logo_url


class InAppProductForm(forms.ModelForm):

    class Meta:
        model = InAppProduct
        fields = ['price']

    def __init__(self, *args, **kwargs):
        super(InAppProductForm, self).__init__(*args, **kwargs)
        self.fields['price'].queryset = Price.objects.active()
