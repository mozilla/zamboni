# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def reset_extensions_translations_locales(apps, schema_editor):
    """Reset the locale field for all translations on existing Extensions. This
    is done to fix bug 1215094: some translations were created with the wrong
    language - the one from the request, instead of the one from the
    default_language field."""

    Extension = apps.get_model('extensions', 'Extension')
    Translation = apps.get_model('translations', 'Translation')
    extensions = Extension.objects.all()
    for extension in extensions:
        translations_ids = filter(
            None, [extension.name_id, extension.description_id])
        lang = extension.default_language.lower()
        Translation.objects.filter(id__in=translations_ids).update(locale=lang)


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0015_extension_author'),
    ]

    operations = [
        migrations.RunPython(reset_extensions_translations_locales),
    ]
