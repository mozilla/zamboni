from django.conf.urls import include, patterns, url

from rest_framework.routers import SimpleRouter

from mkt.abuse.views import (AppAbuseViewSet, ExtensionAbuseViewSet,
                             UserAbuseViewSet, WebsiteAbuseViewSet)

abuse = SimpleRouter()
abuse.register('user', UserAbuseViewSet, base_name='user-abuse')
abuse.register('app', AppAbuseViewSet, base_name='app-abuse')
abuse.register('website', WebsiteAbuseViewSet, base_name='website-abuse')
abuse.register('extension', ExtensionAbuseViewSet, base_name='extension-abuse')


api_patterns = patterns(
    '',
    url('^abuse/', include(abuse.urls)),
)
