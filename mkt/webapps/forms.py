from django import forms
from django.conf import settings
from django.core.files.storage import default_storage as storage

import commonware.log
from tower import ugettext as _

from mkt.site.utils import slug_validator

from .models import BlockedSlug, Webapp


log = commonware.log.getLogger('z.addons')


def clean_slug(slug, instance):
    slug_validator(slug, lower=False)
    slug_field = 'app_slug'

    if slug != getattr(instance, slug_field):
        if Webapp.objects.filter(**{slug_field: slug}).exists():
            raise forms.ValidationError(
                _('This slug is already in use. Please choose another.'))
        if BlockedSlug.blocked(slug):
            raise forms.ValidationError(
                _('The slug cannot be "%s". Please choose another.' % slug))

    return slug


def icons():
    """
    Generates a list of tuples for the default icons for add-ons,
    in the format (psuedo-mime-type, description).
    """
    icons = [('image/jpeg', 'jpeg'), ('image/png', 'png'), ('', 'default')]
    dirs, files = storage.listdir(settings.ADDON_ICONS_DEFAULT_PATH)
    for fname in files:
        if '32' in fname and 'default' not in fname:
            icon_name = fname.split('-')[0]
            icons.append(('icon/%s' % icon_name, icon_name))
    return icons
