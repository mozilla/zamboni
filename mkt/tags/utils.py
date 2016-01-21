from django import forms

from tower import ugettext as _, ungettext as ngettext

import mkt
from mkt.access import acl
from mkt.site.utils import slugify
from mkt.tags.models import Tag


def clean_tags(request, tags, max_tags=None):
    """
    Blocked tags are not allowed.
    Restricted tags can only be edited by Reviewers and Curators.
    """
    target = [slugify(t, spaces=True, lower=True) for t in tags.split(',')]
    target = set(filter(None, target))

    min_len = mkt.MIN_TAG_LENGTH
    max_len = Tag._meta.get_field('tag_text').max_length
    max_tags = max_tags or mkt.MAX_TAGS
    total = len(target)

    blocked = (Tag.objects.values_list('tag_text', flat=True)
               .filter(tag_text__in=target, blocked=True))
    if blocked:
        # L10n: {0} is a single tag or a comma-separated list of tags.
        msg = ngettext(u'Invalid tag: {0}', 'Invalid tags: {0}',
                       len(blocked)).format(', '.join(blocked))
        raise forms.ValidationError(msg)

    restricted = (Tag.objects.values_list('tag_text', flat=True)
                     .filter(tag_text__in=target, restricted=True))
    if restricted and not can_edit_restricted_tags(request):
        # L10n: {0} is a single tag or a comma-separated list of tags.
        msg = ngettext(u'"{0}" is a reserved tag and cannot be used.',
                       u'"{0}" are reserved tags and cannot be used.',
                       len(restricted)).format('", "'.join(restricted))
        raise forms.ValidationError(msg)
    else:
        # Admin's restricted tags don't count towards the limit.
        total = len(target - set(restricted))

    if total > max_tags:
        num = total - max_tags
        msg = ngettext(u'You have {0} too many tags.',
                       u'You have {0} too many tags.', num).format(num)
        raise forms.ValidationError(msg)

    if any(t for t in target if len(t) > max_len):
        raise forms.ValidationError(
            _(u'All tags must be %s characters '
              u'or less after invalid characters are removed.' % max_len))

    if any(t for t in target if len(t) < min_len):
        msg = ngettext(u'All tags must be at least {0} character.',
                       u'All tags must be at least {0} characters.',
                       min_len).format(min_len)
        raise forms.ValidationError(msg)

    return target


def can_edit_restricted_tags(request):
    return (acl.action_allowed(request, 'Apps', 'Edit') or
            acl.action_allowed(request, 'Feed', 'Curate'))
