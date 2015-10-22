from zipfile import ZipFile

from lib.post_request_task.task import task as post_request_task
from mkt.developers.tasks import save_icon
from mkt.site.decorators import use_master
from mkt.site.storage_utils import private_storage


@post_request_task
@use_master
def fetch_icon(pk, version_pk=None, **kw):
    """Take an extension pk and extract 128x128 icon from its zip file, build
    resized PNG copies of it at the dimensions we use, optimize those and store
    them in our public storage.

    When done, `icon_hash` property should be set on the extension."""
    from mkt.extensions.models import Extension

    extension = Extension.objects.get(pk=pk)
    if version_pk:
        version = extension.versions.get(pk=version_pk)
    else:
        version = extension.latest_public_version
    icon_path = version.manifest.get('icons', {}).get('128', '').lstrip('/')
    if not icon_path:
        return
    with private_storage.open(version.file_path) as fd:
        with ZipFile(fd) as zfd:
            icon_contents = zfd.read(icon_path)
    save_icon(extension, icon_contents)
