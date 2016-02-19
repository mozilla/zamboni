import json
import os
import shutil
import tempfile
from base64 import b64decode

from django.conf import settings

import commonware.log
import requests
from django_statsd.clients import statsd
from post_request_task.task import task
from signing_clients.apps import JarExtractor

from mkt.versions.models import Version
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage)


log = commonware.log.getLogger('z.crypto')


class SigningError(Exception):
    pass


def sign_app(src, dest, ids, reviewer=False, local=False):
    """
    Sign a packaged app.

    If `local` is True, we never copy the signed package to remote storage.

    """
    tempname = tempfile.mktemp()
    try:
        return _sign_app(src, dest, ids, reviewer, tempname, local)
    finally:
        try:
            os.unlink(tempname)
        except OSError:
            # If the file has already been removed, don't worry about it.
            pass


def _sign_app(src, dest, ids, reviewer, tempname, local=False):
    """
    Generate a manifest and signature and send signature to signing server to
    be signed.
    """
    active_endpoint = _get_endpoint(reviewer)
    timeout = settings.SIGNED_APPS_SERVER_TIMEOUT

    if not active_endpoint:
        _no_sign(src, dest)
        return

    # Extract necessary info from the archive
    try:
        jar = JarExtractor(
            src, tempname,
            ids,
            omit_signature_sections=settings.SIGNED_APPS_OMIT_PER_FILE_SIGS)
    except:
        log.error('Archive extraction failed. Bad archive?', exc_info=True)
        raise SigningError('Archive extraction failed. Bad archive?')

    log.info('App signature contents: %s' % jar.signatures)

    log.info('Calling service: %s' % active_endpoint)
    try:
        with statsd.timer('services.sign.app'):
            response = requests.post(active_endpoint, timeout=timeout,
                                     files={'file': ('zigbert.sf',
                                                     str(jar.signatures))})
    except requests.exceptions.HTTPError, error:
        # Will occur when a 3xx or greater code is returned.
        log.error('Posting to app signing failed: %s, %s' % (
            error.response.status, error))
        raise SigningError('Posting to app signing failed: %s, %s' % (
            error.response.status, error))

    except:
        # Will occur when some other error occurs.
        log.error('Posting to app signing failed', exc_info=True)
        raise SigningError('Posting to app signing failed')

    if response.status_code != 200:
        log.error('Posting to app signing failed: %s' % response.reason)
        raise SigningError('Posting to app signing failed: %s'
                           % response.reason)

    pkcs7 = b64decode(json.loads(response.content)['zigbert.rsa'])
    try:
        jar.make_signed(pkcs7, sigpath='zigbert')
    except:
        log.error('App signing failed', exc_info=True)
        raise SigningError('App signing failed')

    storage = public_storage  # By default signed packages are public.
    if reviewer:
        storage = private_storage
    elif local:
        storage = local_storage

    copy_stored_file(
        tempname, dest,
        src_storage=local_storage, dst_storage=storage)


def _get_endpoint(reviewer=False):
    """
    Returns the proper API endpoint depending whether we are signing for
    reviewer or for public consumption.
    """
    active = (settings.SIGNED_APPS_REVIEWER_SERVER_ACTIVE if reviewer else
              settings.SIGNED_APPS_SERVER_ACTIVE)
    server = (settings.SIGNED_APPS_REVIEWER_SERVER if reviewer else
              settings.SIGNED_APPS_SERVER)

    if active:
        if not server:
            # If no API endpoint is set. Just ignore this request.
            raise ValueError(
                'Invalid config. The %sserver setting is empty.' % (
                    'reviewer ' if reviewer else ''))
        return server + '/1.0/sign_app'


def _no_sign(src, dst_path):
    # If this is a local development instance, just copy the file around
    # so that everything seems to work locally.
    log.info('Not signing the app, no signing server is active.')

    with public_storage.open(dst_path, 'w') as dst_f:
        shutil.copyfileobj(src, dst_f)


@task
def sign(version_id, reviewer=False, resign=False, **kw):
    version = Version.objects.get(pk=version_id)
    app = version.addon
    log.info('Signing version: %s of app: %s' % (version_id, app))

    if not app.is_packaged:
        log.error('[Webapp:%s] Attempt to sign a non-packaged app.' % app.id)
        raise SigningError('Not packaged')

    try:
        file_obj = version.all_files[0]
    except IndexError:
        log.error(
            '[Webapp:%s] Attempt to sign an app with no files in version.' %
            app.id)
        raise SigningError('No file')

    path = (file_obj.signed_reviewer_file_path if reviewer else
            file_obj.signed_file_path)

    storage = private_storage if reviewer else public_storage

    if storage.exists(path) and not resign:
        log.info('[Webapp:%s] Already signed app exists.' % app.id)
        return path

    if reviewer:
        # Reviewers get a unique 'id' so the reviewer installed app won't
        # conflict with the public app, and also so multiple versions of the
        # same app won't conflict with themselves.
        ids = json.dumps({
            'id': 'reviewer-{guid}-{version_id}'.format(guid=app.guid,
                                                        version_id=version_id),
            'version': version_id
        })
    else:
        ids = json.dumps({
            'id': app.guid,
            'version': version_id
        })
    with statsd.timer('services.sign.app'):
        try:
            # Signing starts with the original packaged app file which is
            # always on private storage.
            sign_app(private_storage.open(file_obj.file_path), path, ids,
                     reviewer)
        except SigningError:
            log.info('[Webapp:%s] Signing failed' % app.id)
            if storage.exists(path):
                storage.delete(path)
            raise
    log.info('[Webapp:%s] Signing complete.' % app.id)
    return path
