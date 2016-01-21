from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import translation

import waffle
from cache_nuggets.lib import memoize
from tower import ugettext as _

import mkt
from mkt.access import acl
from mkt.zadmin.models import get_config


def i18n(request):
    return {
        'LANGUAGES': settings.LANGUAGES,
        'LANG': (settings.LANGUAGE_URL_MAP.get(translation.get_language()) or
                 translation.get_language()),
        'DIR': 'rtl' if translation.get_language_bidi() else 'ltr',
    }


def static_url(request):
    return {'STATIC_URL': settings.STATIC_URL}


@memoize('collect-timings')
def get_collect_timings():
    # The flag has to be enabled for everyone and then we'll use that
    # percentage in the pages.
    percent = 0
    try:
        flag = waffle.models.Flag.objects.get(name='collect-timings')
        if flag.everyone and flag.percent:
            percent = float(flag.percent) / 100.0
    except waffle.models.Flag.DoesNotExist:
        pass
    return percent


def global_settings(request):
    """Store global Marketplace-wide info. used in the header."""
    account_links = []
    tools_links = []
    footer_links = []
    context = {}

    tools_title = _('Tools')

    context['user'] = request.user
    if request.user.is_authenticated():
        context['is_reviewer'] = acl.check_reviewer(request)
        account_links = [
            # TODO: Coming soon with payments.
            # {'text': _('Account History'),
            #  'href': reverse('account.purchases')},
            {'text': _('Account Settings'), 'href': '/settings'},
            {'text': _('Change Password'),
             'href': 'https://login.persona.org/signin'},
            {'text': _('Sign out'), 'href': reverse('users.logout')},
        ]
        if '/developers/' not in request.path:
            tools_links.append({'text': _('Developer Hub'),
                                'href': reverse('ecosystem.landing')})
            if request.user.is_developer:
                tools_links.append({'text': _('My Submissions'),
                                    'href': reverse('mkt.developers.apps')})
        if '/reviewers/' not in request.path and context['is_reviewer']:
            footer_links.append({
                'text': _('Reviewer Tools'),
                'href': reverse('reviewers.apps.queue_pending'),
            })
        if acl.action_allowed(request, 'AccountLookup', '%'):
            footer_links.append({'text': _('Lookup Tool'),
                                 'href': reverse('lookup.home')})
        if acl.action_allowed(request, 'Admin', '%'):
            footer_links.append({'text': _('Admin Tools'),
                                 'href': reverse('zadmin.home')})

        tools_links += footer_links
        logged = True
    else:
        logged = False

    DESKTOP = (getattr(request, 'TABLET', None) or
               not getattr(request, 'MOBILE', None))

    context.update(account_links=account_links,
                   settings=settings,
                   mkt=mkt,
                   tools_links=tools_links,
                   tools_title=tools_title,
                   footer_links=footer_links,
                   ADMIN_MESSAGE=get_config('site_notice'),
                   collect_timings_percent=get_collect_timings(),
                   is_admin=acl.action_allowed(request, 'Apps', 'Edit'),
                   DESKTOP=DESKTOP,
                   logged=logged)
    return context
