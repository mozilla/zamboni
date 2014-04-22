from django.conf.urls import patterns, url

from . import views


urlpatterns = patterns('',
    url('^mozmarket.js$', views.mozmarket_js, name='site.mozmarket_js'),
    url('^robots.txt$', views.robots, name='robots.txt'),

    # Replace opensearch.xml from amo with a specific one for Marketplace.
    url('^opensearch.xml$', views.OpensearchView.as_view(), name='opensearch'),

    # These are the new manifest URLs going forward.
    url('^hosted.webapp$', views.manifest, name='hosted.webapp'),
    url('^packaged.webapp$', views.package_minifest, name='packaged.webapp'),
    url('^marketplace-package.webapp$', views.yogafire_minifest,
        name='packaged-marketplace.webapp'),

    # TODO: Deprecate this in favour of the ones above.
    url('^manifest.webapp$', views.manifest, name='manifest.webapp'),
    url('^minifest.webapp$', views.package_minifest, name='minifest.webapp'),

    url('^timing/record$', views.record, name='mkt.timing.record'),
)
