from django.conf.urls import include, patterns, url
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from amo.urlresolvers import reverse
from . import views


ADDON_ID = r"""(?P<addon_id>[^/<>"']+)"""


urlpatterns = patterns('',
    # AMO stuff.
    url('^$', views.index, name='zadmin.index'),
    url('^models$', lambda r: redirect('admin:index'), name='zadmin.home'),
    url('^addon/manage/%s/$' % ADDON_ID,
        views.addon_manage, name='zadmin.addon_manage'),
    url('^addon/recalc-hash/(?P<file_id>\d+)/', views.recalc_hash,
        name='zadmin.recalc_hash'),
    url('^env$', views.env, name='amo.env'),
    url('^hera', views.hera, name='zadmin.hera'),
    url('^memcache$', views.memcache, name='zadmin.memcache'),
    url('^settings', views.show_settings, name='zadmin.settings'),
    url('^fix-disabled', views.fix_disabled_file, name='zadmin.fix-disabled'),
    url(r'^email_preview/(?P<topic>.*)\.csv$',
        views.email_preview_csv, name='zadmin.email_preview_csv'),

    url('^mail$', views.mail, name='zadmin.mail'),
    url('^email-devs$', views.email_devs, name='zadmin.email_devs'),
    url('^generate-error$', views.generate_error,
        name='zadmin.generate-error'),

    url('^export_email_addresses$', views.export_email_addresses,
        name='zadmin.export_email_addresses'),
    url('^email_addresses_file$', views.email_addresses_file,
        name='zadmin.email_addresses_file'),

    url('^price-tiers$', views.price_tiers, name='zadmin.price_tiers'),

    # The Django admin.
    url('^models/', include(admin.site.urls)),
    url('^models/(?P<app_id>.+)/(?P<model_id>.+)/search.json$',
        views.general_search, name='zadmin.search'),
)


# Hijack the admin's login to use our pages.
def login(request):
    # If someone is already auth'd then they're getting directed to login()
    # because they don't have sufficient permissions.
    if request.user.is_authenticated():
        raise PermissionDenied
    else:
        return redirect('%s?to=%s' % (reverse('users.login'), request.path))


admin.site.login = login
