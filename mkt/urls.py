# -*- coding: utf-8 -*-
from django.conf import settings
from django.conf.urls import include, patterns, url
from django.contrib import admin
from django.shortcuts import redirect
from django.views.decorators.cache import cache_page
from django.views.i18n import javascript_catalog

import mkt
from mkt.account.urls import user_patterns
from mkt.api import oauth
from mkt.detail.views import manifest as mini_manifest
from mkt.developers.views import login
from mkt.extensions.views import mini_manifest as mini_extension_manifest
from mkt.langpacks.views import manifest as mini_langpack_manifest
from mkt.operators.urls import url_patterns as operator_patterns
from mkt.purchase.urls import webpay_services_patterns
from mkt.reviewers.urls import url_patterns as reviewer_url_patterns
from mkt.users.views import logout


# Hardcore monkeypatching action.
import jingo.monkey
jingo.monkey.patch()


admin.autodiscover()

handler403 = 'mkt.site.views.handler403'
handler404 = 'mkt.site.views.handler404'
handler500 = 'mkt.site.views.handler500'


urlpatterns = patterns(
    '',
    # Non-commonplace app pages
    ('^app/%s/' % mkt.APP_SLUG, include('mkt.detail.urls')),
    url('^app/%s/manifest.webapp$' % mkt.ADDON_UUID, mini_manifest,
        name='detail.manifest'),
    url('^langpack/%s/manifest.webapp$' % mkt.ADDON_UUID,
        mini_langpack_manifest, name='langpack.manifest'),
    url('^extension/(?P<uuid>[0-9a-f]{32})/manifest.json$',
        mini_extension_manifest, name='extension.mini_manifest'),

    # Dev Ecosystem
    ('^developers/', include('mkt.ecosystem.urls')),
    ('^ecosystem/', lambda r: redirect('ecosystem.landing', permanent=True)),

    # Files
    ('^files/', include('mkt.files.urls')),

    # Replace the "old" Developer Hub with the "new" Marketplace one.
    ('^developers/', include('mkt.developers.urls')),

    # Submission.
    ('^developers/submit/', include('mkt.submit.urls')),

    # Users.
    ('^users/', include(user_patterns)),

    # Reviewer tools.
    ('^reviewers/', include(reviewer_url_patterns)),

    # Account lookup.
    ('^lookup/', include('mkt.lookup.urls')),

    # Bootstrapped operator dashboard.
    ('^operators/', include(operator_patterns)),

    # Javascript translations.
    url('^jsi18n.js$', cache_page(60 * 60 * 24 * 365)(javascript_catalog),
        {'domain': 'javascript', 'packages': ['zamboni']}, name='jsi18n'),

    # webpay / nav.pay() services.
    ('^services/webpay/', include(webpay_services_patterns)),

    # AMO Marketplace admin (not django admin).
    ('^admin/', include('mkt.zadmin.urls')),

    # Developer Registration Login.
    url('^login$', login, name='users.login'),
    url('^logout$', logout, name='users.logout'),

    url('^oauth/register/$', oauth.access_request,
        name='mkt.developers.oauth_access_request'),

    url('^oauth/token/$', oauth.token_request,
        name='mkt.developers.oauth_token_request'),

    url('^oauth/authorize/$', oauth.authorize,
        name='mkt.developers.oauth_authorize'),

    url('^api/', include('mkt.api.urls')),

    url('^downloads/', include('mkt.downloads.urls')),

    # Try and keep urls without a prefix at the bottom of the list for
    # minor performance reasons.

    # Misc pages.
    ('', include('mkt.commonplace.urls')),
    ('', include('mkt.site.urls')),
)

if settings.TEMPLATE_DEBUG:
    # Remove leading and trailing slashes so the regex matches.
    media_url = settings.MEDIA_URL.lstrip('/').rstrip('/')
    urlpatterns += patterns(
        '',
        (r'^%s/(?P<path>.*)$' % media_url, 'django.views.static.serve',
         {'document_root': settings.MEDIA_ROOT}),
    )

if settings.SERVE_TMP_PATH and settings.DEBUG:
    # Serves any URL like /tmp/* from your local ./tmp/ dir
    urlpatterns += patterns(
        '',
        (r'^tmp/img/(?P<path>.*)$', 'django.views.static.serve',
         {'document_root': settings.TMP_PATH}),
    )
