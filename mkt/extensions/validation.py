import json
from zipfile import BadZipfile

from django.forms import ValidationError
from django.utils.encoding import smart_unicode


from rest_framework.exceptions import ParseError
from tower import ugettext as _

from mkt.files.utils import SafeUnzip
from mkt.site.utils import strip_bom


class ExtensionValidator(object):
    """
    Firefox OS Add-on validator. If validation fails, will raise an instance of
    rest_framework.exceptions.ParseError containing information about the
    error.
    """
    errors = {
        'AUTHOR_NOT_STRING': _(u'The `author` property must be a string.'),
        'AUTHOR_TOO_LONG': _(
            u'The `author` property cannot be longer than 128 characters.'),
        'AUTHOR_TOO_SHORT': _(
            u'The `author` property must be at least 1 character'
            u' long and can not consist of only whitespace characters.'),
        'BAD_CONTENT_TYPE': _(
            u'The file sent has an unsupported content-type'),
        'DESCRIPTION_NOT_STRING': _(
            u'The `description` property must be a string.'),
        'DESCRIPTION_TOO_LONG': _(
            u'The `description` property cannot be '
            u'longer than 132 characters.'),
        'ICONS_DO_NOT_EXIST': _(u'Not all specified icons exist.'),
        'ICONS_NO_128': _(
            u'If defining `icons`, you must include a 128x128 variant.'),
        'ICONS_INVALID_FORMAT': _(u'Only PNG icons are permitted.'),
        'INVALID_JSON': _(
            u"'manifest.json' in the archive is not a valid JSON"
            u" file."),
        'INVALID_JSON_ENCODING': _(
            u"'manifest.json' in the archive is not encoded in UTF-8."),
        'INVALID_ZIP': _(u'The file sent is not a valid ZIP file.'),
        'NAME_MISSING': _(u'There is no `name` property in the manifest.'),
        'NAME_NOT_STRING': _(u'The `name` property must be a string.'),
        'NAME_TOO_LONG': _(
            u'The `name` property cannot be longer than 45 '
            u'characters.'),
        'NAME_TOO_SHORT': _(
            u'The `name` property must be at least 1 character'
            u' long and can not consist of only whitespace characters.'),
        'NO_MANIFEST': _(
            u"The archive does not contain a 'manifest.json' "
            u"file."),
        'VERSION_MISSING': _(
            u'There is no `version` property in the manifest.'),
        'VERSION_NOT_STRING': _(u'The `version` property must be a string.'),
        'VERSION_INVALID': _(
            u'The `version` property must be a string'
            u' containing one to four dot-separated integers each between'
            u' 0 and 65535.'),
    }
    valid_content_types = (
        'application/octet-stream',
        'application/zip',
    )

    def __init__(self, file_obj=None):
        self.file_obj = file_obj
        self.zipfile = None

    def error(self, error_key):
        raise ParseError(detail={
            'key': error_key,
            'message': self.errors[error_key],
        })

    def validate(self):
        """
        Run the full validation suite against the uploaded file:

        * Ensure that it is a valid zip file.
        * Ensure that it contains a valid manifest.json file.
        * Validate the manifest fields against the spec.

        Return the manifest contents (as dict).
        """
        self.manifest = self.validate_file(self.file_obj)
        self.data = self.validate_json(self.manifest)
        self.validate_name(self.data)
        self.validate_description(self.data)
        self.validate_version(self.data)
        self.validate_author(self.data)
        self.validate_icons(self.data)
        # self.validate_icon_files(self.data)
        return self.data

    def validate_file(self, file_obj):
        """
        Verify that the upload is a valid zip file that contains a
        manifest.json file.
        """
        if file_obj.content_type not in self.valid_content_types:
            self.error('BAD_CONTENT_TYPE')
        try:
            self.zipfile = SafeUnzip(file_obj)
            try:
                # Will throw ValidationError if necessary.
                self.zipfile.is_valid()
            except ValidationError as e:
                raise ParseError(unicode(e))
            except (BadZipfile, IOError):
                self.error('INVALID_ZIP')
            manifest = self.zipfile.extract_path('manifest.json')
        except KeyError:
            self.error('NO_MANIFEST')
        return manifest

    def validate_json(self, contents):
        """
        Verify that the enclosed manifest.json is a valid and parsable JSON
        file.
        """
        try:
            # We support only UTF-8 encoded manifests.
            decoded_data = smart_unicode(strip_bom(contents))
        except UnicodeDecodeError:
            self.error('INVALID_JSON_ENCODING')
        try:
            return json.loads(decoded_data)
        except ValueError:
            self.error('INVALID_JSON')

    def validate_name(self, manifest_json):
        """
        Ensure that the name property of the manifest exists and is a string
        between 1 and 45 characters long.

        In addition, even though it's allowed in the spec, we consider the name
        invalid (too short) if it contains only whitespace characters.

        https://developer.chrome.com/extensions/manifest/name
        """
        try:
            name = manifest_json['name']
        except KeyError:
            self.error('NAME_MISSING')
        if not isinstance(name, basestring):
            self.error('NAME_NOT_STRING')
        if len(name.strip()) < 1:
            self.error('NAME_TOO_SHORT')
        if len(name) > 45:
            self.error('NAME_TOO_LONG')

    def validate_description(self, manifest_json):
        """
        Ensures that, if present, the description property is no longer than
        132 characters.

        https://developer.chrome.com/extensions/manifest/description
        """
        if 'description' in manifest_json:
            description = manifest_json['description']
            if not isinstance(description, basestring):
                self.error('DESCRIPTION_NOT_STRING')
            if len(description.strip()) > 132:
                self.error('DESCRIPTION_TOO_LONG')

    def validate_version(self, manifest_json):
        """
        Ensure that the version property of the manifest exists and is a string
        containing one to four dot-separated integers, each between 0 and
        65535, with no leading zeros."""
        try:
            version = manifest_json['version']
        except KeyError:
            self.error('VERSION_MISSING')
        if not isinstance(version, basestring):
            self.error('VERSION_NOT_STRING')
        splitted = version.split('.')
        if len(splitted) > 4:
            # Too many dots.
            self.error('VERSION_INVALID')
        for version_component in splitted:
            try:
                number = int(version_component)
                if version_component.startswith('0') and number != 0:
                    # Leading zeros are forbidden.
                    self.error('VERSION_INVALID')
                if number < 0 or number > 65535:
                    # All numbers must be between 0 and 65535 inclusive.
                    self.error('VERSION_INVALID')
            except ValueError:
                # Not a valid number.
                self.error('VERSION_INVALID')

    def validate_author(self, manifest_json):
        """
        Ensures that, if present, the author property is no longer than
        128 characters.
        """
        if 'author' in manifest_json:
            author = manifest_json['author']
            # Author must not be empty/only whitespace if present, since we'll
            # use it as link text.
            if not isinstance(author, basestring):
                self.error('AUTHOR_NOT_STRING')
            if len(author.strip()) < 1:
                self.error('AUTHOR_TOO_SHORT')
            if len(author) > 128:
                self.error('AUTHOR_TOO_LONG')

    def validate_icons(self, manifest_json):
        """
        Validate the `icons` property in the manifest:

        * Ensure that, if the icons property is present, a 128px icon is
          provided.
        * Ensure that each icon referenced has a .png extension.
        """
        icons = manifest_json.get('icons', {})
        if icons:
            if '128' not in icons:
                self.error('ICONS_NO_128')
            for size, path in icons.iteritems():
                if not path.endswith('.png'):
                    self.error('ICONS_INVALID_FORMAT')

    def validate_icon_files(self, manifest_json):
        """
        In turn, validate each icon file referenced by the `icons` property of
        the manifest:

        * Ensure that the file exists in the zip.
        * Ensure that it is a valid PNG file.
        * Ensure that it has the claimed dimensions.
        * Ensure that it is square.
        """
        icons = manifest_json.get('icons', {})
        return icons
