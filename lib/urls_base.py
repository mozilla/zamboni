from django.conf import settings
from django.conf.urls import include, patterns, url
from django.contrib import admin
from django.shortcuts import redirect
from django.views.decorators.cache import cache_page
from django.views.i18n import javascript_catalog

from amo.urlresolvers import reverse
from amo.utils import urlparams

import versions.urls


admin.autodiscover()

handler403 = 'amo.views.handler403'
handler404 = 'amo.views.handler404'
handler500 = 'amo.views.handler500'


urlpatterns = patterns('',
    # AMO homepage or Marketplace Developer Hub? Choose your destiny.
    url('^$', settings.HOME, name='home'),

    # Add-ons.
    ('', include('addons.urls')),

    # Tags.
    ('', include('tags.urls')),

    # Collections.
    ('', include('bandwagon.urls')),

    # Files
    ('^files/', include('files.urls')),

    # Downloads.
    ('^downloads/', include(versions.urls.download_patterns)),

    # Users
    ('', include('users.urls')),

    # Developer Hub.
    ('^developers/', include('devhub.urls')),

    # AMO admin (not django admin).
    ('^admin/', include('zadmin.urls')),

    # App versions.
    ('pages/appversions/', include('applications.urls')),

    # Services
    ('', include('amo.urls')),

    # Paypal
    ('^services/', include('paypal.urls')),

    # Search
    ('^search/', include('search.urls')),

    # Javascript translations.
    url('^jsi18n.js$', cache_page(60 * 60 * 24 * 365)(javascript_catalog),
        {'domain': 'javascript', 'packages': ['zamboni']}, name='jsi18n'),

    # Review spam.
    url('^reviews/spam/$', 'reviews.views.spam', name='addons.reviews.spam'),

    ('^reviews/display/(\d+)',
      lambda r, id: redirect('addons.reviews.list', id, permanent=True)),

    ('^reviews/add/(\d+)',
      lambda r, id: redirect('addons.reviews.add', id, permanent=True)),

    ('^users/info/(\d+)',
     lambda r, id: redirect('users.profile', id, permanent=True)),

    # Redirect persona/xxx
    ('^getpersonas$',
     lambda r: redirect('http://www.getpersonas.com/gallery/All/Popular',
                        permanent=True)),

    url('^persona/(?P<persona_id>\d+)', 'addons.views.persona_redirect',
        name='persona'),

    # Redirect top-tags to tags/top
    ('^top-tags/?',
     lambda r: redirect('tags.top_cloud', permanent=True)),

    ('^addons/versions/(\d+)/?$',
     lambda r, id: redirect('addons.versions', id, permanent=True)),

    ('^addons/versions/(\d+)/format:rss$',
     lambda r, id: redirect('addons.versions.rss', id, permanent=True)),

    # Legacy redirect. Requires a view to get extra data not provided in URL.
    ('^versions/updateInfo/(?P<version_id>\d+)',
     'versions.views.update_info_redirect'),

    ('^addons/reviews/(\d+)/format:rss$',
     lambda r, id: redirect('addons.reviews.list.rss', id, permanent=True)),

    ('^search-engines.*$',
     lambda r: redirect(urlparams(reverse('search.search'), atype=4),
                        permanent=True)),

    ('^addons/contribute/(\d+)/?$',
     lambda r, id: redirect('addons.contribute', id, permanent=True)),

)

if settings.TEMPLATE_DEBUG:
    # Remove leading and trailing slashes so the regex matches.
    media_url = settings.MEDIA_URL.lstrip('/').rstrip('/')
    urlpatterns += patterns('',
        (r'^%s/(?P<path>.*)$' % media_url, 'django.views.static.serve',
         {'document_root': settings.MEDIA_ROOT}),
    )

if settings.SERVE_TMP_PATH and settings.DEBUG:
    urlpatterns += patterns('',
        (r'^tmp/(?P<path>.*)$', 'django.views.static.serve',
         {'document_root': settings.TMP_PATH}),
    )
