import os
import os.path
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connections

import commonware.log

import mkt
from mkt.files.models import FileUpload
from mkt.site.decorators import use_master
from mkt.versions.models import Version
from mkt.webapps.models import Webapp


log = commonware.log.getLogger('mkt.fireplace.commands')


class Command(BaseCommand):
    help = (
        'Upload and sign a new version of the specified app.\n'
        'Syntax:\n\t./manage.py upload_new_marketplace_package'
        ' <app-slug> <path-to-zip>')

    def info(self, msg):
        log.info(msg)
        self.stdout.write(msg)
        self.stdout.flush()

    def upload(self, webapp, path):
        """Create FileUpload instance from local file."""
        self.info('Creating FileUpload...')
        package_file = open(path)
        package_size = os.stat(path).st_size
        upload = FileUpload()
        upload.user = webapp.authors.all()[0]
        upload.add_file(package_file.read(), 'marketplace-package.zip',
                        package_size)
        self.info('Created FileUpload %s.' % upload)
        return upload

    def create_version(self, webapp, upload):
        """Create new Version instance from a FileUpload instance"""
        self.info('Creating new Version...')
        version = Version.from_upload(upload, webapp)
        self.info('Created new Version %s.' % version)
        return version

    def sign_and_publicise(self, webapp, version):
        """Sign the version we just created and make it public."""
        # Note: most of this is lifted from mkt/reviewers/utils.py, but without
        # the dependency on `request` and isolating only what we need.
        self.info('Signing version...')
        webapp.sign_if_packaged(version.pk)
        self.info('Signing version %s done.' % version)
        self.info('Setting File to public...')
        file_ = version.all_files[0]
        file_.update(_signal=False, datestatuschanged=datetime.now(),
                     reviewed=datetime.now(), status=mkt.STATUS_PUBLIC)
        self.info('File for version %s set to public.' % version)
        self.info('Setting version %s as the current version...' % version)
        version.update(_signal=False, reviewed=datetime.now())
        webapp.update_version(_signal=False)
        self.info('Set version %s as the current version.' % version)

    @use_master
    def handle(self, *args, **options):
        if len(args) != 2:
            raise CommandError(self.help)

        slug = args[0]
        path = args[1]

        if not path.endswith('.zip'):
            raise CommandError('File does not look like a zip file.')

        if not os.path.exists(path):
            raise CommandError('File does not exist')

        webapp = Webapp.objects.get(app_slug=slug)

        # Wrap everything we're doing in a transaction, if there is an uncaught
        # exception everything will be rolled back. We force a connect() call
        # first to work around django-mysql-pool problems (autocommit state is
        # not properly reset, messing up transaction.atomic() blocks).
        connections['default'].connect()
        with transaction.atomic():
            upload = self.upload(webapp, path)
            version = self.create_version(webapp, upload)
            self.sign_and_publicise(webapp, version)

            self.info('Excellent! Version %s is the now live \o/' % version)
