from django.conf.urls import include, patterns, url
from django.shortcuts import redirect

from lib.misc.urlconf_decorator import decorate

import mkt
from mkt.site.decorators import use_master
from . import views


# These URLs start with /developers/submit/app/<app_slug>/.
submit_apps_patterns = patterns(
    '',
    url('^details/%s$' % mkt.APP_SLUG, views.details,
        name='submit.app.details'),
    url('^done/%s$' % mkt.APP_SLUG, views.done, name='submit.app.done'),
    url('^resume/%s$' % mkt.APP_SLUG, views.resume, name='submit.app.resume'),
)


urlpatterns = decorate(use_master, patterns(
    '',
    # Legacy redirects for app submission.
    ('^app', lambda r: redirect('submit.app')),
    # ^ So we can avoid an additional redirect below.
    ('^app/.*', lambda r: redirect(r.path.replace('/developers/app',
                                                  '/developers', 1))),
    ('^manifest$', lambda r: redirect('submit.app', permanent=True)),

    # App submission.
    url('^$', views.submit, name='submit.app'),
    url('^terms$', views.terms, name='submit.app.terms'),

    ('', include(submit_apps_patterns)),
))
