import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile

from django import forms
from django.conf import settings
from django.utils.translation import trans_real as translation

from tower import ugettext as _

from mkt.site.storage_utils import private_storage
from mkt.site.utils import rm_local_tmp_dir, strip_bom
from mkt.translations.utils import to_language


log = logging.getLogger('files.utils')


SIGNED_RE = re.compile('^META\-INF/(\w+)\.(rsa|sf)$')


def get_filepath(fileorpath):
    """Get the actual file path of fileorpath if it's a FileUpload object."""
    if hasattr(fileorpath, 'path'):  # FileUpload
        return fileorpath.path
    return fileorpath


def get_file(fileorpath):
    """
    Get a file-like object, whether given a FileUpload object or an
    UploadedFile.
    """
    if hasattr(fileorpath, 'path'):  # FileUpload
        return private_storage.open(fileorpath.path)
    if hasattr(fileorpath, 'name'):
        return fileorpath
    raise ValueError("not a file or upload")


class WebAppParser(object):
    langpacks_allowed = False

    def extract_locale(self, locales, key, default=None):
        """Gets a locale item based on key.

        For example, given this:

            locales = {'en': {'foo': 1, 'bar': 2},
                       'it': {'foo': 1, 'bar': 2}}

        You can get english foo like:

            self.extract_locale(locales, 'foo', 'en')

        """
        ex = {}
        for loc, data in locales.iteritems():
            ex[loc] = data.get(key, default)
        return ex

    def get_json_data(self, fileorpath):
        fp = get_file(fileorpath)
        if zipfile.is_zipfile(fp):
            zf = SafeUnzip(fp)
            zf.is_valid()  # Raises forms.ValidationError if problems.
            try:
                data = zf.extract_path('manifest.webapp')
            except KeyError:
                raise forms.ValidationError(
                    _('The file "manifest.webapp" was not found at the root '
                      'of the packaged app archive.'))
        else:
            file_ = get_file(fileorpath)
            file_.seek(0)
            data = file_.read()
            file_.close()

        return WebAppParser.decode_manifest(data)

    @classmethod
    def decode_manifest(cls, manifest):
        """
        Returns manifest, stripped of BOMs and UTF-8 decoded, as Python dict.
        """
        try:
            data = strip_bom(manifest)
            # Marketplace only supports UTF-8 encoded manifests.
            decoded_data = data.decode('utf-8')
        except (ValueError, UnicodeDecodeError) as exc:
            msg = 'Error parsing manifest (encoding: utf-8): %s: %s'
            log.error(msg % (exc.__class__.__name__, exc))
            raise forms.ValidationError(
                _('Could not decode the webapp manifest file. '
                  'Check your manifest file for special non-utf-8 '
                  'characters.'))

        try:
            return json.loads(decoded_data)
        except Exception:
            raise forms.ValidationError(
                _('The webapp manifest is not valid JSON.'))

    def parse(self, fileorpath):
        data = self.get_json_data(fileorpath)

        if not self.langpacks_allowed and data.get('role') == 'langpack':
            raise forms.ValidationError(
                _(u'The "langpack" role is invalid for Web Apps. Please submit'
                  u' this app as a language pack instead.'))

        loc = data.get('default_locale', translation.get_language())
        default_locale = self.trans_locale(loc)
        locales = data.get('locales', {})
        if type(locales) == list:
            raise forms.ValidationError(
                _('Your specified app locales are not in the correct format.'))

        localized_descr = self.extract_locale(locales, 'description',
                                              default='')
        if 'description' in data:
            localized_descr.update({default_locale: data['description']})

        localized_name = self.extract_locale(locales, 'name',
                                             default=data['name'])
        localized_name.update({default_locale: data['name']})

        developer_info = data.get('developer', {})
        developer_name = developer_info.get('name')
        if not developer_name:
            # Missing developer name shouldn't happen if validation took place,
            # but let's be explicit about this just in case.
            raise forms.ValidationError(
                _("Developer name is required in the manifest in order to "
                  "display it on the app's listing."))

        return {'guid': None,
                'name': self.trans_all_locales(localized_name),
                'developer_name': developer_name,
                'description': self.trans_all_locales(localized_descr),
                'version': data.get('version', '1.0'),
                'default_locale': default_locale,
                'origin': data.get('origin')}

    def trans_locale(self, locale):
        return to_language(settings.SHORTER_LANGUAGES.get(locale, locale))

    def trans_all_locales(self, locale_dict):
        trans = {}
        for key, item in locale_dict.iteritems():
            key = self.trans_locale(key)
            trans[key] = item
        return trans


class SafeUnzip(object):
    def __init__(self, source, mode='r'):
        self.source = source
        self.info = None
        self.mode = mode

    def is_valid(self, fatal=True):
        """
        Runs some overall archive checks.
        fatal: if the archive is not valid and fatal is True, it will raise
               an error, otherwise it will return False.
        """
        try:
            self.zip = zipfile.ZipFile(self.source, self.mode)
        except (zipfile.BadZipfile, IOError):
            if fatal:
                log.info('Error extracting', exc_info=True)
                raise
            return False

        self.info = self.zip.infolist()
        sum_size = 0

        for info in self.info:
            if '..' in info.filename or info.filename.startswith('/'):
                log.error(u'Extraction error, invalid file name (%s) in '
                          u'archive: %s' % (info.filename, self.source))
                # L10n: {0} is the name of the invalid file.
                raise forms.ValidationError(
                    _(u'Invalid file name in archive: {0}').format(
                        info.filename))

            if info.file_size > settings.FILE_UNZIP_SIZE_LIMIT:
                log.error(u'Extraction error, file too big (%s) in archive '
                          u'%s' % (info.filename, self.source))
                # L10n: {0} is the name of the invalid file.
                raise forms.ValidationError(
                    _(u'File exceeding size limit in archive: {0}').format(
                        info.filename))

            sum_size += info.file_size

        if sum_size > settings.FILE_UNZIP_SIZE_LIMIT:
            log.error('Extraction error, total size of files too big (%s)'
                      ' in archive: %s' % (sum_size, self.source, ))
            raise forms.ValidationError(_(
                'Total size of files exeeding limit in archive: {0}').format(
                info.filename))
        return True

    def is_signed(self):
        """Tells us if an addon is signed."""
        finds = []
        for info in self.info:
            match = SIGNED_RE.match(info.filename)
            if match:
                name, ext = match.groups()
                # If it's rsa or sf, just look for the opposite.
                if (name, {'rsa': 'sf', 'sf': 'rsa'}[ext]) in finds:
                    return True
                finds.append((name, ext))

    def extract_path(self, path):
        """Given a path, extracts the content at path."""
        return self.zip.read(path)

    def extract_info_to_dest(self, info, dest):
        """Extracts the given info to a directory and checks the file size."""
        self.zip.extract(info, dest)
        dest = os.path.join(dest, info.filename)
        if not os.path.isdir(dest):
            # Directories consistently report their size incorrectly.
            size = os.stat(dest)[stat.ST_SIZE]
            if size != info.file_size:
                log.error('Extraction error, uncompressed size: %s, %s not %s'
                          % (self.source, size, info.file_size))
                raise forms.ValidationError(_('Invalid archive.'))

    def extract_to_dest(self, dest):
        """Extracts the zip file to a directory."""
        for info in self.info:
            self.extract_info_to_dest(info, dest)

    def close(self):
        if hasattr(self, 'zip'):
            self.zip.close()


def extract_zip(source):
    """Extracts the zip file."""
    tempdir = tempfile.mkdtemp()

    zip = SafeUnzip(source)
    try:
        if zip.is_valid():
            zip.extract_to_dest(tempdir)
    except:
        rm_local_tmp_dir(tempdir)
        raise

    return tempdir


def copy_over(source, dest):
    """
    Copies from the source to the destination, removing the destination
    if it exists and is a directory.
    """
    if os.path.exists(dest) and os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    # mkdtemp will set the directory permissions to 700
    # for the webserver to read them, we need 755
    os.chmod(dest, stat.S_IRWXU | stat.S_IRGRP |
             stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    shutil.rmtree(source)


def parse_addon(pkg, addon=None):
    """
    pkg is a filepath or a django.core.files.UploadedFile
    or files.models.FileUpload.
    """
    return WebAppParser().parse(pkg)


def _get_hash(filename, block_size=2 ** 20, hash=hashlib.md5):
    """Returns an MD5 hash for a filename."""
    f = private_storage.open(filename, 'rb')
    hash_ = hash()
    while True:
        data = f.read(block_size)
        if not data:
            break
        hash_.update(data)
    return hash_.hexdigest()


def get_md5(filename, **kw):
    return _get_hash(filename, **kw)
