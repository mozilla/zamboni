import csp.views
from waffle.views import wafflejs

from django.conf.urls import include, patterns, url
from django.views.decorators.cache import never_cache

from . import views, install

services_patterns = patterns('',
    url('^monitor(.json)?$', never_cache(views.monitor),
        name='amo.monitor'),
    url('^loaded$', never_cache(views.loaded), name='amo.loaded'),
    url('^csp/policy$', csp.views.policy, name='amo.csp.policy'),
    url('^csp/report$', views.cspreport, name='amo.csp.report'),
    url('^timing/record$', views.record, name='amo.timing.record'),
    url('^install.php$', install.install, name='api.install'),
)

urlpatterns = patterns('',
    url('^robots.txt$', views.robots, name='robots.txt'),
    url(r'^wafflejs$', wafflejs, name='wafflejs'),
    ('^services/', include(services_patterns)),
)
