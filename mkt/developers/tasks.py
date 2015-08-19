# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import urlparse
import uuid
import zipfile

from django import forms
from django.conf import settings
from django.core.files.storage import default_storage as storage

import requests
from appvalidator import validate_app, validate_packaged_app
from celery import task
from django_statsd.clients import statsd
from PIL import Image
from tower import ugettext as _

import mkt
from lib.post_request_task.task import task as post_request_task
from mkt.constants import APP_PREVIEW_SIZES
from mkt.constants.regions import REGIONS_CHOICES_ID_DICT
from mkt.files.helpers import copyfileobj
from mkt.files.models import File, FileUpload, FileValidation
from mkt.files.utils import SafeUnzip
from mkt.site.decorators import set_modified_on, use_master
from mkt.site.helpers import absolutify
from mkt.site.mail import send_mail_jinja
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, public_storage)
from mkt.site.utils import (remove_icons, remove_promo_imgs, resize_image,
                            strip_bom)
from mkt.webapps.models import AddonExcludedRegion, Preview, Webapp
from mkt.webapps.utils import iarc_get_app_info


log = logging.getLogger('z.mkt.developers.task')


CT_URL = (
    'https://developer.mozilla.org/docs/Web/Apps/Manifest#Serving_manifests'
)

REQUESTS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Mobile; rv:18.0) Gecko/18.0 Firefox/18.0'
}


@post_request_task
@use_master
def validator(upload_id, **kw):
    if not settings.VALIDATE_ADDONS:
        return None
    log.info(u'[FileUpload:%s] Validating app.' % upload_id)
    try:
        upload = FileUpload.objects.get(pk=upload_id)
    except FileUpload.DoesNotExist:
        log.info(u'[FileUpload:%s] Does not exist.' % upload_id)
        return

    try:
        validation_result = run_validator(upload.path, url=kw.get('url'))
        if upload.validation:
            # If there's any preliminary validation result, merge it with the
            # actual validation result.
            dec_prelim_result = json.loads(upload.validation)
            if 'prelim' in dec_prelim_result:
                dec_validation_result = json.loads(validation_result)
                # Merge the messages.
                dec_validation_result['messages'] += (
                    dec_prelim_result['messages'])
                # Merge the success value.
                if dec_validation_result['success']:
                    dec_validation_result['success'] = (
                        dec_prelim_result['success'])
                # Merge the error count (we only raise errors, not warnings).
                dec_validation_result['errors'] += dec_prelim_result['errors']

                # Put the validation result back into JSON.
                validation_result = json.dumps(dec_validation_result)

        upload.validation = validation_result
        upload.save()  # We want to hit the custom save().
    except Exception:
        # Store the error with the FileUpload job, then raise
        # it for normal logging.
        tb = traceback.format_exception(*sys.exc_info())
        upload.update(task_error=''.join(tb))
        # Don't raise if we're being eager, setting the error is enough.
        if not settings.CELERY_ALWAYS_EAGER:
            raise


@task
@use_master
def file_validator(file_id, **kw):
    if not settings.VALIDATE_ADDONS:
        return None
    log.info(u'[File:%s] Validating file.' % file_id)
    try:
        file = File.objects.get(pk=file_id)
    except File.DoesNotExist:
        log.info(u'[File:%s] Does not exist.' % file_id)
        return
    # Unlike upload validation, let the validator raise an exception if there
    # is one.
    result = run_validator(file.file_path, url=file.version.addon.manifest_url)
    return FileValidation.from_json(file, result)


def run_validator(file_path, url=None):
    """A pre-configured wrapper around the app validator."""

    temp_path = None
    # Make a copy of the file since we can't assume the
    # uploaded file is on the local filesystem.
    temp_path = tempfile.mktemp()
    with open(temp_path, 'wb') as local_f:
        with private_storage.open(file_path) as remote_f:
            copyfileobj(remote_f, local_f)

    with statsd.timer('mkt.developers.validator'):
        is_packaged = zipfile.is_zipfile(temp_path)
        if is_packaged:
            log.info(u'Running `validate_packaged_app` for path: %s'
                     % (file_path))
            with statsd.timer('mkt.developers.validate_packaged_app'):
                return validate_packaged_app(
                    temp_path,
                    market_urls=settings.VALIDATOR_IAF_URLS,
                    timeout=settings.VALIDATOR_TIMEOUT,
                    spidermonkey=settings.SPIDERMONKEY)
        else:
            log.info(u'Running `validate_app` for path: %s' % (file_path))
            with statsd.timer('mkt.developers.validate_app'):
                return validate_app(open(temp_path).read(),
                                    market_urls=settings.VALIDATOR_IAF_URLS,
                                    url=url)

    # Clean up copied files.
    os.unlink(temp_path)


def _hash_file(fd):
    return hashlib.md5(fd.read()).hexdigest()[:8]


@post_request_task
@set_modified_on
def resize_icon(src, dst, sizes, storage=private_storage, **kw):
    """Resizes addon/websites icons."""
    log.info('[1@None] Resizing icon: %s' % dst)

    try:
        for s in sizes:
            size_dst = '%s-%s.png' % (dst, s)
            resize_image(src, size_dst, (s, s),
                         remove_src=False, storage=storage)
            pngcrush_image.delay(size_dst, **kw)

        with storage.open(src) as fd:
            icon_hash = _hash_file(fd)
        storage.delete(src)

        log.info('Icon resizing completed for: %s' % dst)
        return {'icon_hash': icon_hash}
    except Exception, e:
        log.error("Error resizing icon: %s; %s" % (e, dst))


@post_request_task
@set_modified_on
def resize_promo_imgs(src, dst, sizes, locally=False, **kw):
    """Resizes webapp/website promo imgs."""
    log.info('[1@None] Resizing promo imgs: %s' % dst)
    try:
        for s in sizes:
            size_dst = '%s-%s.png' % (dst, s)
            # Crop only to the width, keeping the aspect ratio.
            resize_image(src, size_dst, (s, 0),
                         remove_src=False, locally=locally)
            pngcrush_image.delay(size_dst, **kw)

        if locally:
            with open(src) as fd:
                promo_img_hash = _hash_file(fd)
            os.remove(src)
        else:
            with storage.open(src) as fd:
                promo_img_hash = _hash_file(fd)
            storage.delete(src)

        log.info('Promo img hash resizing completed for: %s' % dst)
        return {'promo_img_hash': promo_img_hash}
    except Exception, e:
        log.error("Error resizing promo img hash: %s; %s" % (e, dst))


@task
@set_modified_on
def pngcrush_image(src, hash_field='image_hash', **kw):
    """
    Optimizes a PNG image by running it through Pngcrush. Returns hash.

    src -- filesystem image path
    hash_field -- field name to save the new hash on instance if passing
                  instance through set_modified_on
    """
    log.info('[1@None] Optimizing image: %s' % src)
    tmp_src = tempfile.NamedTemporaryFile(suffix='.png')
    with public_storage.open(src) as srcf:
        shutil.copyfileobj(srcf, tmp_src)
        tmp_src.seek(0)
    try:
        # pngcrush -ow has some issues, use a temporary file and do the final
        # renaming ourselves.
        suffix = '.opti.png'
        tmp_path = '%s%s' % (os.path.splitext(tmp_src.name)[0], suffix)
        cmd = [settings.PNGCRUSH_BIN, '-q', '-rem', 'alla', '-brute',
               '-reduce', '-e', suffix, tmp_src.name]
        sp = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = sp.communicate()
        if sp.returncode != 0:
            log.error('Error optimizing image: %s; %s' % (src, stderr.strip()))
            pngcrush_image.retry(args=[src], kwargs=kw, max_retries=3)
            return False

        # Return hash for set_modified_on.
        with open(tmp_path) as fd:
            image_hash = _hash_file(fd)

        copy_stored_file(tmp_path, src, src_storage=local_storage,
                         dest_storage=public_storage)
        log.info('Image optimization completed for: %s' % src)
        os.remove(tmp_path)
        tmp_src.close()
        return {
            hash_field: image_hash
        }

    except Exception, e:
        log.error('Error optimizing image: %s; %s' % (src, e))
    return {}


@post_request_task
@set_modified_on
def resize_preview(src, pk, **kw):
    """Resizes preview images and stores the sizes on the preview."""
    instance = Preview.objects.get(pk=pk)
    thumb_dst, full_dst = instance.thumbnail_path, instance.image_path
    sizes = instance.sizes or {}
    log.info('[1@None] Resizing preview and storing size: %s' % thumb_dst)
    try:
        thumbnail_size = APP_PREVIEW_SIZES[0][:2]
        image_size = APP_PREVIEW_SIZES[1][:2]
        with storage.open(src, 'rb') as fp:
            size = Image.open(fp).size
        if size[0] > size[1]:
            # If the image is wider than tall, then reverse the wanted size
            # to keep the original aspect ratio while still resizing to
            # the correct dimensions.
            thumbnail_size = thumbnail_size[::-1]
            image_size = image_size[::-1]

        if kw.get('generate_thumbnail', True):
            sizes['thumbnail'] = resize_image(src, thumb_dst,
                                              thumbnail_size,
                                              remove_src=False)
        if kw.get('generate_image', True):
            sizes['image'] = resize_image(src, full_dst,
                                          image_size,
                                          remove_src=False)
        instance.sizes = sizes
        instance.save()
        log.info('Preview resized to: %s' % thumb_dst)

        # Remove src file now that it has been processed.
        try:
            os.remove(src)
        except OSError:
            pass

        return True

    except Exception, e:
        log.error("Error saving preview: %s; %s" % (e, thumb_dst))


def _fetch_content(url):
    with statsd.timer('developers.tasks.fetch_content'):
        try:
            res = requests.get(url, timeout=30, stream=True,
                               headers=REQUESTS_HEADERS)

            if not 200 <= res.status_code < 300:
                statsd.incr('developers.tasks.fetch_content.error')
                raise Exception('An invalid HTTP status code was returned.')

            if not res.headers.keys():
                statsd.incr('developers.tasks.fetch_content.error')
                raise Exception('The HTTP server did not return headers.')

            statsd.incr('developers.tasks.fetch_content.success')
            return res
        except requests.RequestException as e:
            statsd.incr('developers.tasks.fetch_content.error')
            log.error('fetch_content connection error: %s' % e)
            raise Exception('The file could not be retrieved.')


class ResponseTooLargeException(Exception):
    pass


def get_content_and_check_size(response, max_size):
    # Read one extra byte. Reject if it's too big so we don't have issues
    # downloading huge files.
    content = response.iter_content(chunk_size=max_size + 1).next()
    if len(content) > max_size:
        raise ResponseTooLargeException('Too much data.')
    return content


def save_icon(obj, icon_content):
    """
    Saves the icon for `obj` to its final destination. `obj` can be an app or a
    website.
    """
    tmp_dst = os.path.join(settings.TMP_PATH, 'icon', uuid.uuid4().hex)
    with storage.open(tmp_dst, 'wb') as fd:
        fd.write(icon_content)

    dirname = obj.get_icon_dir()
    destination = os.path.join(dirname, '%s' % obj.pk)
    remove_icons(destination)
    icon_hash = resize_icon(tmp_dst, destination, mkt.CONTENT_ICON_SIZES,
                            set_modified_on=[obj])

    # Need to set icon type so .get_icon_url() works normally
    # submit step 4 does it through AppFormMedia, but we want to beat them to
    # the punch. resize_icon outputs pngs so we know it's 'image/png'.
    obj.icon_hash = icon_hash['icon_hash']  # In case, we're running not async.
    obj.icon_type = 'image/png'
    obj.save()


def save_promo_imgs(obj, img_content):
    """
    Saves the promo image for `obj` to its final destination.
    `obj` can be an app or a website.
    """
    tmp_dst = os.path.join(settings.TMP_PATH, 'promo_imgs', uuid.uuid4().hex)
    with storage.open(tmp_dst, 'wb') as fd:
        fd.write(img_content)

    dirname = obj.get_promo_img_dir()
    destination = os.path.join(dirname, '%s' % obj.pk)
    remove_promo_imgs(destination)
    resize_promo_imgs(
        tmp_dst, destination, mkt.PROMO_IMG_SIZES,
        set_modified_on=[obj])


@post_request_task
@use_master
def fetch_icon(pk, file_pk=None, **kw):
    """
    Downloads a webapp icon from the location specified in the manifest.

    Returns False if icon was not able to be retrieved

    If `file_pk` is not provided it will use the file from the app's
    `current_version`.

    """
    webapp = Webapp.objects.get(pk=pk)
    log.info(u'[1@None] Fetching icon for webapp %s.' % webapp.name)
    if file_pk:
        file_obj = File.objects.get(pk=file_pk)
    else:
        file_obj = (webapp.current_version and
                    webapp.current_version.all_files[0])
    manifest = webapp.get_manifest_json(file_obj)

    if not manifest or 'icons' not in manifest:
        # Set the icon type to empty.
        webapp.update(icon_type='')
        return

    try:
        biggest = max(int(size) for size in manifest['icons'])
    except ValueError:
        log.error('No icon to fetch for webapp "%s"' % webapp.name)
        return False

    icon_url = manifest['icons'][str(biggest)]
    if icon_url.startswith('data:image'):
        image_string = icon_url.split('base64,')[1]
        content = base64.decodestring(image_string)
    else:
        if webapp.is_packaged:
            # Get icons from package.
            if icon_url.startswith('/'):
                icon_url = icon_url[1:]
            try:
                zf = SafeUnzip(storage.open(file_obj.file_path))
                zf.is_valid()
                content = zf.extract_path(icon_url)
            except (KeyError, forms.ValidationError):  # Not found in archive.
                log.error(u'[Webapp:%s] Icon %s not found in archive'
                          % (webapp, icon_url))
                return False
        else:
            if not urlparse.urlparse(icon_url).scheme:
                icon_url = webapp.origin + icon_url

            try:
                response = _fetch_content(icon_url)
            except Exception, e:
                log.error(u'[Webapp:%s] Failed to fetch icon for webapp: %s'
                          % (webapp, e))
                # Set the icon type to empty.
                webapp.update(icon_type='')
                return False

            try:
                content = get_content_and_check_size(
                    response, settings.MAX_ICON_UPLOAD_SIZE)
            except ResponseTooLargeException:
                log.warning(u'[Webapp:%s] Icon exceeds maximum size.' % webapp)
                return False

    log.info('Icon fetching completed for app "%s"; saving icon' % webapp.name)
    save_icon(webapp, content)


def failed_validation(*messages, **kwargs):
    """Return a validation object that looks like the add-on validator."""
    upload = kwargs.pop('upload', None)
    if upload is None or not upload.validation:
        msgs = []
    else:
        msgs = json.loads(upload.validation)['messages']

    for msg in messages:
        msgs.append({'type': 'error', 'message': msg, 'tier': 1})

    return json.dumps({'errors': sum(1 for m in msgs if m['type'] == 'error'),
                       'success': False,
                       'messages': msgs,
                       'prelim': True})


def _fetch_manifest(url, upload=None):
    def fail(message, upload=None):
        if upload is None:
            # If `upload` is None, that means we're using one of @washort's old
            # implementations that expects an exception back.
            raise Exception(message)
        upload.update(validation=failed_validation(message, upload=upload))

    try:
        response = _fetch_content(url)
    except Exception, e:
        log.error('Failed to fetch manifest from %r: %s' % (url, e))
        fail(_('No manifest was found at that URL. Check the address and try '
               'again.'), upload=upload)
        return

    ct = response.headers.get('content-type', '')
    if not ct.startswith('application/x-web-app-manifest+json'):
        fail(_('Manifests must be served with the HTTP header '
               '"Content-Type: application/x-web-app-manifest+json". See %s '
               'for more information.') % CT_URL,
             upload=upload)

    try:
        max_webapp_size = settings.MAX_WEBAPP_UPLOAD_SIZE
        content = get_content_and_check_size(response, max_webapp_size)
    except ResponseTooLargeException:
        fail(_('Your manifest must be less than %s bytes.') % max_webapp_size,
             upload=upload)
        return

    try:
        content.decode('utf_8')
    except (UnicodeDecodeError, UnicodeEncodeError), exc:
        log.info('Manifest decode error: %s: %s' % (url, exc))
        fail(_('Your manifest file was not encoded as valid UTF-8.'),
             upload=upload)
        return

    # Get the individual parts of the content type.
    ct_split = map(str.strip, ct.split(';'))
    if len(ct_split) > 1:
        # Figure out if we've got a charset specified.
        kv_pairs = dict(tuple(p.split('=', 1)) for p in ct_split[1:] if
                        '=' in p)
        if 'charset' in kv_pairs and kv_pairs['charset'].lower() != 'utf-8':
            fail(_("The manifest's encoding does not match the charset "
                   'provided in the HTTP Content-Type.'),
                 upload=upload)

    content = strip_bom(content)
    return content


@post_request_task
@use_master
def fetch_manifest(url, upload_pk=None, **kw):
    log.info(u'[1@None] Fetching manifest: %s.' % url)
    upload = FileUpload.objects.get(pk=upload_pk)

    content = _fetch_manifest(url, upload)
    if content is None:
        return

    upload.add_file([content], url, len(content))
    # Send the upload to the validator.
    validator(upload.pk, url=url)


@task
def region_email(ids, region_ids, **kw):
    regions = [REGIONS_CHOICES_ID_DICT[id] for id in region_ids]
    region_names = regions = sorted([unicode(r.name) for r in regions])

    # Format the region names with commas and fanciness.
    if len(regions) == 2:
        suffix = 'two'
        region_names = ' '.join([regions[0], _(u'and'), regions[1]])
    else:
        if len(regions) == 1:
            suffix = 'one'
        elif len(regions) > 2:
            suffix = 'many'
            region_names[-1] = _(u'and') + ' ' + region_names[-1]
        region_names = ', '.join(region_names)

    log.info('[%s@%s] Emailing devs about new region(s): %s.' %
             (len(ids), region_email.rate_limit, region_names))

    for id_ in ids:
        log.info('[Webapp:%s] Emailing devs about new region(s): %s.' %
                 (id_, region_names))

        product = Webapp.objects.get(id=id_)
        to = set(product.authors.values_list('email', flat=True))

        if len(regions) == 1:
            subject = _(
                u'{region} region added to the Firefox Marketplace').format(
                    region=regions[0])
        else:
            subject = _(u'New regions added to the Firefox Marketplace')

        dev_url = absolutify(product.get_dev_url('edit'),
                             settings.SITE_URL) + '#details'
        context = {'app': product.name,
                   'regions': region_names,
                   'dev_url': dev_url}
        send_mail_jinja('%s: %s' % (product.name, subject),
                        'developers/emails/new_regions_%s.ltxt' % suffix,
                        context, recipient_list=to,
                        perm_setting='app_regions')


@task
@use_master
def region_exclude(ids, region_ids, **kw):
    regions = [REGIONS_CHOICES_ID_DICT[id] for id in region_ids]
    region_names = ', '.join(sorted([unicode(r.name) for r in regions]))

    log.info('[%s@%s] Excluding new region(s): %s.' %
             (len(ids), region_exclude.rate_limit, region_names))

    for id_ in ids:
        log.info('[Webapp:%s] Excluding region(s): %s.' %
                 (id_, region_names))
        for region in regions:
            # Already excluded? Swag!
            AddonExcludedRegion.objects.get_or_create(addon_id=id_,
                                                      region=region.id)


@task
def save_test_plan(f, filename, addon):
    dst_root = os.path.join(settings.ADDONS_PATH, str(addon.id))
    dst = os.path.join(dst_root, filename)
    with open(dst, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)


@task
@use_master
def refresh_iarc_ratings(ids, **kw):
    """
    Refresh old or corrupt IARC ratings by re-fetching the certificate.
    """
    for app in Webapp.objects.filter(id__in=ids):
        data = iarc_get_app_info(app)

        if data.get('rows'):
            row = data['rows'][0]

            # We found a rating, so store the id and code for future use.
            app.set_descriptors(row.get('descriptors', []))
            app.set_interactives(row.get('interactives', []))
            app.set_content_ratings(row.get('ratings', {}))
