import json
import logging
import zipfile

from django import forms
from django.utils.encoding import smart_unicode

from tower import ugettext as _

from mkt.files.utils import get_file, SafeUnzip
from mkt.site.utils import cached_property, strip_bom
from mkt.translations.utils import to_language


log = logging.getLogger('extensions.utils')


class ExtensionParser(object):
    def __init__(self, fileorpath):
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
        """Parse archive and return extension data as expected by the models.

        May raise forms.ValidationError."""
        raw_data = self.manifest_contents
        data = {}

        required_fields = ('name', 'version')
        for field in required_fields:
            if not raw_data.get(field):
                raise forms.ValidationError(
                    _(u'The "%s" field is missing or empty in the'
                      u' add-on manifest.' % field))
            data[field] = raw_data[field]

        extra_fields = ('description',)
        for field in extra_fields:
            if field in raw_data:
                data[field] = raw_data[field]

        default_locale = raw_data.get('default_locale')
        if default_locale:
            # We actually need language (e.g. "en-US") for translations, not
            # locale (e.g. "en_US"). The extension contains locales though, not
            # languages, so transform the field in the manifest before adding
            # it to the data we'll pass to the model.
            data['default_language'] = to_language(default_locale)

        data['manifest'] = self.manifest_contents
        return data
