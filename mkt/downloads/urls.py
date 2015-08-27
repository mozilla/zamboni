from django.conf.urls import patterns, url

from mkt.downloads.views import download_file
from mkt.extensions.views import download as download_extension
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
        download_extension, name='extension.download'),
)
