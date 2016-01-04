# -*- coding: utf-8 -*-
from django import forms

from django.utils.translation import ugettext as _

from mkt.files.utils import WebAppParser


class LanguagePackParser(WebAppParser):
    langpacks_allowed = True

    def __init__(self, instance=None):
        self.instance = instance

    def parse(self, upload):
        """Parse the FileUpload passed in argument and return langpack data.
        May raise forms.ValidationError()"""
        output = super(LanguagePackParser, self).parse(upload)
        data = self.get_json_data(upload)

        if data.get('role') != 'langpack':
            raise forms.ValidationError(
                _(u'Your language pack should contain "role": "langpack".'))

        languages_provided = data.get('languages-provided', {}).keys()
        if len(languages_provided) < 1:
            raise forms.ValidationError(
                _(u'Your language pack must contain one language in '
                  u'`languages-provided` object.'))
        if len(languages_provided) > 1:
            # For now, refuse langpacks containing more than one language.
            raise forms.ValidationError(
                _(u'Your language pack contains too many languages. Only one '
                  u'language per pack is supported.'))

        languages_target = data.get('languages-target', {}).values()
        if len(languages_target) < 1:
            raise forms.ValidationError(
                _(u'Your language pack must contain one language in '
                  u'`languages-target` object.'))
        if len(languages_target) > 1:
            # For now, refuse langpacks containing more than one target.
            raise forms.ValidationError(
                _(u'Your language pack contains too many targets. Only one '
                  u'target per pack is supported.'))

        version = data.get('version')
        if version is None:
            raise forms.ValidationError(
                _(u'Your language pack should contain a version.'))
        if self.instance and self.instance.version == version:
            raise forms.ValidationError(
                _(u'Your language pack version must be different to the one '
                  u'you are replacing.'))

        # We don't really care about the base fields from the parent, but it
        # helps tests.
        output.update({
            'language': languages_provided[0],
            'fxos_version': languages_target[0],
            'version': version,
        })
        return output
