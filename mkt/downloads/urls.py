from django.conf.urls import patterns, url

from mkt.downloads.views import download_file
from mkt.extensions import views as extensions_views
from mkt.langpacks.views import download as download_langpack


urlpatterns = patterns(
    '',
    # .* at the end to match filenames.
    # /file/:id/type:attachment
    url(r'^file/(?P<file_id>\d+)(?:/type:(?P<type>\w+))?(?:/.*)?',
        download_file, name='downloads.file'),
    url(r'^langpack/(?P<langpack_id>[0-9a-f]{32})'
        '(?:/type:(?P<type>\w+))?(?:/.*)?',
        download_langpack, name='langpack.download'),
    url(r'^extension/(?P<uuid>[0-9a-f]{32})/(?P<filename>[^/<>"\']+)$',
        extensions_views.download_signed,
        name='extension.download_signed'),
    url(r'^extension/unsigned/(?P<uuid>[0-9a-f]{32})/'
        r'(?P<filename>[^/<>"\']+)$',
        extensions_views.download_unsigned,
        name='extension.download_unsigned'),
)
