from django import forms
from django.conf import settings
from django.core.files.storage import default_storage as storage

import commonware.log
from tower import ugettext as _, ungettext as ngettext

import amo
from amo.utils import slug_validator, slugify
from mkt.access import acl
from mkt.tags.models import Tag

from .models import Addon, BlacklistedSlug


log = commonware.log.getLogger('z.addons')


def clean_slug(slug, instance):
    slug_validator(slug, lower=False)
    slug_field = 'app_slug'

    if slug != getattr(instance, slug_field):
        if Addon.objects.filter(**{slug_field: slug}).exists():
            raise forms.ValidationError(
                _('This slug is already in use. Please choose another.'))
        if BlacklistedSlug.blocked(slug):
            raise forms.ValidationError(
                _('The slug cannot be "%s". Please choose another.' % slug))

    return slug


def clean_tags(request, tags):
    target = [slugify(t, spaces=True, lower=True) for t in tags.split(',')]
    target = set(filter(None, target))

    min_len = amo.MIN_TAG_LENGTH
    max_len = Tag._meta.get_field('tag_text').max_length
    max_tags = amo.MAX_TAGS
    total = len(target)

    blacklisted = (Tag.objects.values_list('tag_text', flat=True)
                      .filter(tag_text__in=target, blacklisted=True))
    if blacklisted:
        # L10n: {0} is a single tag or a comma-separated list of tags.
        msg = ngettext('Invalid tag: {0}', 'Invalid tags: {0}',
                       len(blacklisted)).format(', '.join(blacklisted))
        raise forms.ValidationError(msg)

    restricted = (Tag.objects.values_list('tag_text', flat=True)
                     .filter(tag_text__in=target, restricted=True))
    if not acl.action_allowed(request, 'Apps', 'Edit'):
        if restricted:
            # L10n: {0} is a single tag or a comma-separated list of tags.
            msg = ngettext('"{0}" is a reserved tag and cannot be used.',
                           '"{0}" are reserved tags and cannot be used.',
                           len(restricted)).format('", "'.join(restricted))
            raise forms.ValidationError(msg)
    else:
        # Admin's restricted tags don't count towards the limit.
        total = len(target - set(restricted))

    if total > max_tags:
        num = total - max_tags
        msg = ngettext('You have {0} too many tags.',
                       'You have {0} too many tags.', num).format(num)
        raise forms.ValidationError(msg)

    if any(t for t in target if len(t) > max_len):
        raise forms.ValidationError(_('All tags must be %s characters '
                'or less after invalid characters are removed.' % max_len))

    if any(t for t in target if len(t) < min_len):
        msg = ngettext("All tags must be at least {0} character.",
                       "All tags must be at least {0} characters.",
                       min_len).format(min_len)
        raise forms.ValidationError(msg)

    return target


def icons():
    """
    Generates a list of tuples for the default icons for add-ons,
    in the format (psuedo-mime-type, description).
    """
    icons = [('image/jpeg', 'jpeg'), ('image/png', 'png'), ('', 'default')]
    dirs, files = storage.listdir(settings.ADDON_ICONS_DEFAULT_PATH)
    for fname in files:
        if '32' in fname and not 'default' in fname:
            icon_name = fname.split('-')[0]
            icons.append(('icon/%s' % icon_name, icon_name))
    return icons
