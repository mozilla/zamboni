 # -*- coding: utf-8 -*-
from django import forms

from tower import ugettext as _

from mkt.files.utils import WebAppParser


class LanguagePackParser(WebAppParser):
    def parse(self, upload):
        """Parse the FileUpload passed in argument and return langpack data.
        May raise forms.ValidationError()"""
        # At the moment, we don't care about most of the manifest for
        # langpacks so we simply extract the minimum we require ; in the future
        # we might want to call the parent's parse() method and have a way to
        # deal with extra stuff in the child.
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

        output = {
            'language': languages_provided[0],
            'fxos_version': languages_target[0],
            'version': data.get('version', '1.0'),
        }
        return output
