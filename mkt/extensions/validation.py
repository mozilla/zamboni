import json
from zipfile import BadZipfile, ZipFile

from rest_framework.exceptions import ParseError
from tower import ugettext as _


class ExtensionValidator(object):
    """
    Firefox OS Add-on validator. If validation fails, will raise an instance of
    rest_framework.exceptions.ParseError containing information about the
    error.
    """
    errors = {
        'BAD_CONTENT_TYPE': _('The file sent has an unsupported content-type'),
        'INVALID_JSON': _(("'manifest.json' in the archive is not a valid JSON"
                           " file.")),
        'INVALID_ZIP': _('The file sent is not a valid ZIP file.'),
        'NAME_MISSING': _('There is no `name` property in the manifest.'),
        'NAME_NOT_STRING': _('The `name` property must be a string.'),
        'NAME_TOO_LONG': _(('The `name` property cannot be longer than 45 '
                            'characters.')),
        'NAME_TOO_SHORT': _(('The `name` property must be at least 1 character'
                             ' long.')),
        'NO_MANIFEST': _(("The archive does not contain a 'manifest.json' "
                          "file.")),
    }
    valid_content_types = (
        'application/octet-stream',
        'application/zip',
    )

    def __init__(self, file_obj=None):
        """
        Validate the uploaded file:

        * Ensure that it is a valid zip file.
        * Ensure that it contains a valid manifest.json file.
        * Validate the manifest against the spec.
        """
        self.file = file_obj
        self.manifest_file = None
        self.manifest_json = None

    def validate(self):
        """
        Run the full validation suite.
        """
        self.manifest = self.validate_file(self.file)
        self.json = self.validate_json(self.manifest)
        self.validate_name(self.json)

    def validate_file(self, file_obj):
        """
        Verify that the upload is a valid zip file that contains a
        manifest.json file.
        """
        if file_obj.content_type not in self.valid_content_types:
            raise ParseError(self.errors['BAD_CONTENT_TYPE'])
        try:
            with ZipFile(file_obj, 'r') as z:
                manifest = z.read('manifest.json')
        except BadZipfile:
            raise ParseError(self.errors['INVALID_ZIP'])
        except KeyError:
            raise ParseError(self.errors['NO_MANIFEST'])
        return manifest

    def validate_json(self, contents):
        """
        Verify that the enclosed manifest.json is a valid and parsable JSON
        file.
        """
        try:
            return json.loads(contents)
        except ValueError:
            raise ParseError(self.errors['INVALID_JSON'])

    def validate_name(self, manifest_json):
        """
        Ensure that the name property of the manifest exists and is a string
        between 1 and 45 characters long.

        https://developer.chrome.com/extensions/manifest/name#name
        """
        try:
            name = manifest_json['name']
        except KeyError:
            raise ParseError(self.errors['NAME_MISSING'])
        if not isinstance(name, basestring):
            raise ParseError(self.errors['NAME_NOT_STRING'])
        if len(name) < 1:
            raise ParseError(self.errors['NAME_TOO_SHORT'])
        if len(name) > 45:
            raise ParseError(self.errors['NAME_TOO_LONG'])
