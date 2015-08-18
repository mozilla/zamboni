import json
import logging
import zipfile

from django import forms
from django.utils.encoding import smart_unicode

from tower import ugettext as _

from mkt.files.utils import get_file, SafeUnzip
from mkt.site.utils import cached_property, strip_bom


log = logging.getLogger('extensions.utils')


class ExtensionParser(object):
    def __init__(self, fileorpath, instance=None):
        self.instance = instance
        self.fileorpath = fileorpath

    @cached_property
    def manifest_contents(self):
        fp = get_file(self.fileorpath)
        if zipfile.is_zipfile(fp):
            zf = SafeUnzip(fp)
            zf.is_valid()  # Raises forms.ValidationError if problems.
            try:
                data = zf.extract_path('manifest.json')
            except KeyError:
                raise forms.ValidationError(
                    _('The file "manifest.json" was not found at the root '
                      'of the zip archive.'))
        else:
            raise forms.ValidationError(
                _('Addons need to be packaged into a valid zip archive.'))

        return self.decode_manifest(data)

    def decode_manifest(self, manifest_data):
        """
        Returns manifest, stripped of BOMs and UTF-8 decoded, as Python dict.
        """
        try:
            data = strip_bom(manifest_data)
            # Marketplace only supports UTF-8 encoded manifests.
            decoded_data = smart_unicode(data)
        except (ValueError, UnicodeDecodeError) as exc:
            msg = 'Error parsing manifest (encoding: utf-8): %s: %s'
            log.error(msg % (exc.__class__.__name__, exc))
            raise forms.ValidationError(
                _('Could not decode the addon manifest file. '
                  'Check your manifest file for special non-utf-8 '
                  'characters.'))

        try:
            return json.loads(decoded_data)
        except ValueError:
            raise forms.ValidationError(
                _('The addon manifest is not valid JSON.'))

    def parse(self):
        """Parse archive and return extension data.
         May raise forms.ValidationError()"""
        data = self.manifest_contents
        output = {}

        required_fields = ('name', 'version')
        for field in required_fields:
            if not data.get(field):
                raise forms.ValidationError(
                    _(u'The "%s" field is missing or empty in the'
                      u' add-on manifest.' % field))
            output[field] = data[field]

        allowed_fields = ('author', 'default_locale', 'description', 'icons')
        for field in allowed_fields:
            if field in data:
                output[field] = data[field]

        return output
