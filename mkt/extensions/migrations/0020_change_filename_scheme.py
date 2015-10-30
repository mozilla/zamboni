# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os.path

from django.conf import settings
from django.db import migrations

from mkt.site.storage_utils import (move_stored_file, private_storage,
                                    public_storage)


def move_files_to_their_new_locations(apps, schema_editor):
    ExtensionVersion = apps.get_model('extensions', 'ExtensionVersion')
    versions = ExtensionVersion.objects.all()
    for version in versions:
        # We lost the version number on old deleted versions, nothing we
        # can do about those. It's fine.
        if version.deleted:
            continue

        # Migrations have no access to custom properties and methods, so we
        # have to re-generate file paths.
        unsigned_prefix = os.path.join(
            settings.EXTENSIONS_PATH, str(version.extension.pk))
        signed_prefix = os.path.join(
            settings.SIGNED_EXTENSIONS_PATH, str(version.extension.pk))
        signed_reviewer_prefix = os.path.join(
            settings.EXTENSIONS_PATH, str(version.extension.pk), 'reviewers')
        filename = 'extension-%s.zip' % version.version

        # Original paths have the version number in them.
        original_unsigned_file_path = os.path.join(unsigned_prefix, filename)
        original_signed_file_path = os.path.join(signed_prefix, filename)
        original_reviewer_signed_file_path = os.path.join(
            signed_reviewer_prefix, filename)

        # New paths use the version pk instead, which will always be available.
        new_filename = 'extension-%s.zip' % version.pk
        new_unsigned_file_path = os.path.join(unsigned_prefix, new_filename)
        new_signed_file_path = os.path.join(signed_prefix, new_filename)
        new_reviewer_signed_file_path = os.path.join(
            signed_reviewer_prefix, new_filename)

        # Do the actual moving.
        if private_storage.exists(original_unsigned_file_path):
            move_stored_file(
                original_unsigned_file_path, new_unsigned_file_path)
        if private_storage.exists(original_reviewer_signed_file_path):
            move_stored_file(
                original_reviewer_signed_file_path,
                new_reviewer_signed_file_path)
        if public_storage.exists(original_signed_file_path):
            move_stored_file(
                original_signed_file_path, new_signed_file_path,
                src_storage=public_storage, dst_storage=public_storage)


class Migration(migrations.Migration):

    dependencies = [
        ('extensions', '0019_extension_icon_hash'),
    ]

    operations = [
        migrations.RunPython(move_files_to_their_new_locations)
    ]
