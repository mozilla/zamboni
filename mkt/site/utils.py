import codecs
import datetime
import itertools
import imp
import operator
import os
import random
import re
import shutil
import time
import unicodedata
import urllib
import uuid

from django import http
from django.conf import settings
from django.core import paginator
from django.core.cache import cache
from django.core.serializers import json
from django.core.urlresolvers import reverse
from django.core.validators import validate_slug, ValidationError
from django.db.models.signals import post_save
from django.http import HttpRequest
from django.utils import translation
from django.utils.encoding import smart_str, smart_unicode
from django.utils.functional import Promise
from django.utils.http import urlquote
from django.utils.importlib import import_module

import bleach
import chardet
import commonware.log
import jingo
import jinja2
import pytz
from cef import log_cef as _log_cef
from easy_thumbnails import processors
from elasticsearch_dsl.search import Search
from PIL import Image

import mkt
from lib.utils import static_url
from mkt.api.paginator import ESPaginator
from mkt.constants.applications import DEVICE_TYPES
from mkt.site.storage_utils import (local_storage, private_storage,
                                    public_storage, storage_is_remote)
from mkt.translations.models import Translation


# Copied from jingo 0.7.1 -- loader in 0.8.1 is broken on python 2
def load_helpers():
    """Try to import ``helpers.py`` from each app in INSTALLED_APPS."""
    # We want to wait as long as possible to load helpers so there aren't any
    # weird circular imports with jingo.
    if jingo._helpers_loaded:
        return
    jingo._helpers_loaded = True

    from jingo import helpers  # noqa

    for app in settings.INSTALLED_APPS:
        try:
            app_path = import_module(app).__path__
        except AttributeError:
            continue

        try:
            imp.find_module('helpers', app_path)
        except ImportError:
            continue

        import_module('%s.helpers' % app)

jingo.load_helpers = load_helpers
# Install gettext functions into Jingo's Jinja2 environment.
env = jingo.get_env()
env.install_gettext_translations(translation, newstyle=True)


def days_ago(n):
    return datetime.datetime.now() - datetime.timedelta(days=n)


log = commonware.log.getLogger('z.mkt')


def epoch(t):
    """Date/Time converted to seconds since epoch"""
    if not hasattr(t, 'tzinfo'):
        return
    return int(time.mktime(append_tz(t).timetuple()))


def append_tz(t):
    tz = pytz.timezone(settings.TIME_ZONE)
    return tz.localize(t)


def sorted_groupby(seq, key):
    """
    Given a sequence, we sort it and group it by a key.

    key should be a string (used with attrgetter) or a function.
    """
    if not hasattr(key, '__call__'):
        key = operator.attrgetter(key)
    return itertools.groupby(sorted(seq, key=key), key=key)


def paginate(request, queryset, per_page=20, count=None):
    """
    Get a Paginator, abstracting some common paging actions.

    If you pass ``count``, that value will be used instead of calling
    ``.count()`` on the queryset.  This can be good if the queryset would
    produce an expensive count query.
    """
    p = (ESPaginator if isinstance(queryset, Search)
         else paginator.Paginator)(queryset, per_page)

    if count is not None:
        p._count = count

    # Get the page from the request, make sure it's an int.
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        page = 1

    # Get a page of results, or the first page if there's a problem.
    try:
        paginated = p.page(page)
    except (paginator.EmptyPage, paginator.InvalidPage):
        paginated = p.page(1)

    paginated.url = u'%s?%s' % (request.path, request.GET.urlencode())
    return paginated


class JSONEncoder(json.DjangoJSONEncoder):

    def default(self, obj):
        unicodable = (Translation, Promise)

        if isinstance(obj, unicodable):
            return unicode(obj)

        return super(JSONEncoder, self).default(obj)


def chunked(seq, n):
    """
    Yield successive n-sized chunks from seq.

    >>> for group in chunked(range(8), 3):
    ...     print group
    [0, 1, 2]
    [3, 4, 5]
    [6, 7]
    """
    seq = iter(seq)
    while 1:
        rv = list(itertools.islice(seq, 0, n))
        if not rv:
            break
        yield rv


def _urlencode(items):
    """A Unicode-safe URLencoder."""
    try:
        return urllib.urlencode(items)
    except UnicodeEncodeError:
        return urllib.urlencode([(k, smart_str(v)) for k, v in items])


# Extra characters outside of alphanumerics that we'll allow.
SLUG_OK = '-_~'


def slugify(s, ok=SLUG_OK, lower=True, spaces=False, delimiter='-'):
    # L and N signify letter/number.
    # http://www.unicode.org/reports/tr44/tr44-4.html#GC_Values_Table
    rv = []
    for c in smart_unicode(s):
        cat = unicodedata.category(c)[0]
        if cat in 'LN' or c in ok:
            rv.append(c)
        if cat == 'Z':  # space
            rv.append(' ')
    new = ''.join(rv).strip()
    if not spaces:
        new = re.sub('[-\s]+', delimiter, new)
    return new.lower() if lower else new


def slug_validator(s, ok=SLUG_OK, lower=True, spaces=False, delimiter='-',
                   message=validate_slug.message, code=validate_slug.code):
    """
    Raise an error if the string has any punctuation characters.

    Regexes don't work here because they won't check alnums in the right
    locale.
    """
    if not (s and slugify(s, ok, lower, spaces, delimiter) == s):
        raise ValidationError(message, code=code)


def resize_image(src, dst, size=None, remove_src=True,
                 src_storage=private_storage, dst_storage=public_storage):
    """
    Resizes and image from src, to dst. Returns width and height.
    """
    if src == dst:
        raise Exception("src and dst can't be the same: %s" % src)

    with src_storage.open(src, 'rb') as fp:
        im = Image.open(fp)
        im = im.convert('RGBA')
        if size:
            im = processors.scale_and_crop(im, size)
    with dst_storage.open(dst, 'wb') as fp:
        im.save(fp, 'png')

    if remove_src:
        src_storage.delete(src)

    return im.size


def remove_icons(destination):
    for size in mkt.CONTENT_ICON_SIZES:
        filename = '%s-%s.png' % (destination, size)
        if public_storage.exists(filename):
            public_storage.delete(filename)


def remove_promo_imgs(destination):
    for size in mkt.PROMO_IMG_SIZES:
        filename = '%s-%s.png' % (destination, size)
        if public_storage.exists(filename):
            public_storage.delete(filename)


class ImageCheck(object):

    def __init__(self, image):
        self._img = image

    def is_image(self):
        try:
            self._img.seek(0)
            self.img = Image.open(self._img)
            # PIL doesn't tell us what errors it will raise at this point,
            # just "suitable ones", so let's catch them all.
            self.img.verify()
            return True
        except:
            log.error('Error decoding image', exc_info=True)
            return False

    def is_animated(self, size=100000):
        if not self.is_image():
            return False

        img = self.img
        if img.format == 'PNG':
            self._img.seek(0)
            data = ''
            while True:
                chunk = self._img.read(size)
                if not chunk:
                    break
                data += chunk
                acTL, IDAT = data.find('acTL'), data.find('IDAT')
                if acTL > -1 and acTL < IDAT:
                    return True
            return False
        elif img.format == 'GIF':
            # Animated gifs will have either a duration or loop information.
            return 'duration' in img.info or 'loop' in img.info


def get_file_response(request, path, content=None, status=None,
                      content_type='application/octet-stream', etag=None,
                      public=True):
    if storage_is_remote():
        storage = public_storage if public else private_storage
        if not storage.exists(path):
            raise http.Http404
        # Note: The `content_type` and `etag` will have no effect here. It
        # should be set when saving the item to S3.
        return http.HttpResponseRedirect(storage.url(path))
    else:
        return HttpResponseSendFile(request, path, content_type=content_type,
                                    etag=etag)


class HttpResponseSendFile(http.HttpResponse):

    def __init__(self, request, path, content=None, status=None,
                 content_type='application/octet-stream', etag=None):
        self.request = request
        self.path = path
        super(HttpResponseSendFile, self).__init__('', status=status,
                                                   content_type=content_type)
        if settings.XSENDFILE:
            self[settings.XSENDFILE_HEADER] = path
        if etag:
            self['ETag'] = '"%s"' % etag

    def __iter__(self):
        if settings.XSENDFILE:
            return iter([])

        chunk = 4096
        fp = local_storage.open(self.path, 'rb')
        if 'wsgi.file_wrapper' in self.request.META:
            return self.request.META['wsgi.file_wrapper'](fp, chunk)
        else:
            self['Content-Length'] = local_storage.size(self.path)

            def wrapper():
                while 1:
                    data = fp.read(chunk)
                    if not data:
                        break
                    yield data
            return wrapper()


def redirect_for_login(request):
    # We can't use urlparams here, because it escapes slashes,
    # which a large number of tests don't expect
    url = '%s?to=%s' % (reverse('users.login'),
                        urlquote(request.get_full_path()))
    return http.HttpResponseRedirect(url)


def cache_ns_key(namespace, increment=False):
    """
    Returns a key with namespace value appended. If increment is True, the
    namespace will be incremented effectively invalidating the cache.

    Memcache doesn't have namespaces, but we can simulate them by storing a
    "%(key)s_namespace" value. Invalidating the namespace simply requires
    editing that key. Your application will no longer request the old keys,
    and they will eventually fall off the end of the LRU and be reclaimed.
    """
    ns_key = 'ns:%s' % namespace
    if increment:
        try:
            ns_val = cache.incr(ns_key)
        except ValueError:
            log.info('Cache increment failed for key: %s. Resetting.' % ns_key)
            ns_val = epoch(datetime.datetime.now())
            cache.set(ns_key, ns_val, None)
    else:
        ns_val = cache.get(ns_key)
        if ns_val is None:
            ns_val = epoch(datetime.datetime.now())
            cache.set(ns_key, ns_val, None)
    return '%s:%s' % (ns_val, ns_key)


def smart_path(string):
    """Returns a string you can pass to path.path safely."""
    if os.path.supports_unicode_filenames:
        return smart_unicode(string)
    return smart_str(string)


def log_cef(name, severity, env, *args, **kwargs):
    """Simply wraps the cef_log function so we don't need to pass in the config
    dictionary every time.  See bug 707060.  env can be either a request
    object or just the request.META dictionary"""

    c = {'cef.product': getattr(settings, 'CEF_PRODUCT', 'AMO'),
         'cef.vendor': getattr(settings, 'CEF_VENDOR', 'Mozilla'),
         'cef.version': getattr(settings, 'CEF_VERSION', '0'),
         'cef.device_version': getattr(settings, 'CEF_DEVICE_VERSION', '0'),
         'cef.file': getattr(settings, 'CEF_FILE', 'syslog'), }

    # The CEF library looks for some things in the env object like
    # REQUEST_METHOD and any REMOTE_ADDR stuff.  Django not only doesn't send
    # half the stuff you'd expect, but it specifically doesn't implement
    # readline on its FakePayload object so these things fail.  I have no idea
    # if that's outdated code in Django or not, but andym made this
    # <strike>awesome</strike> less crappy so the tests will actually pass.
    # In theory, the last part of this if() will never be hit except in the
    # test runner.  Good luck with that.
    if isinstance(env, HttpRequest):
        r = env.META.copy()
        if 'PATH_INFO' in r:
            r['PATH_INFO'] = env.build_absolute_uri(r['PATH_INFO'])
    elif isinstance(env, dict):
        r = env
    else:
        r = {}
    if settings.USE_HEKA_FOR_CEF:
        return settings.HEKA.cef(name, severity, r, *args, config=c, **kwargs)
    else:
        return _log_cef(name, severity, r, *args, config=c, **kwargs)


def escape_all(v, linkify=True):
    """Escape html in JSON value, including nested items."""
    if isinstance(v, basestring):
        v = jinja2.escape(smart_unicode(v))
        if linkify:
            v = bleach.linkify(v, callbacks=[bleach.callbacks.nofollow])
        return v
    elif isinstance(v, list):
        for i, lv in enumerate(v):
            v[i] = escape_all(lv, linkify=linkify)
    elif isinstance(v, dict):
        for k, lv in v.iteritems():
            v[k] = escape_all(lv, linkify=linkify)
    elif isinstance(v, Translation):
        v = jinja2.escape(smart_unicode(v.localized_string))
    return v


def strip_bom(data):
    """
    Strip the BOM (byte order mark) from byte string `data`.

    Returns a new byte string.
    """
    for bom in (codecs.BOM_UTF32_BE,
                codecs.BOM_UTF32_LE,
                codecs.BOM_UTF16_BE,
                codecs.BOM_UTF16_LE,
                codecs.BOM_UTF8):
        if data.startswith(bom):
            data = data[len(bom):]
            break
    return data


def smart_decode(s):
    """Guess the encoding of a string and decode it."""
    if isinstance(s, unicode):
        return s
    enc_guess = chardet.detect(s)
    try:
        return s.decode(enc_guess['encoding'])
    except (UnicodeDecodeError, TypeError), exc:
        msg = 'Error decoding string (encoding: %r %.2f%% sure): %s: %s'
        log.error(msg % (enc_guess['encoding'],
                         enc_guess['confidence'] * 100.0,
                         exc.__class__.__name__, exc))
        return unicode(s, errors='replace')


def rm_local_tmp_dir(path):
    """Remove a local temp directory.

    This is just a wrapper around shutil.rmtree(). Use it to indicate you are
    certain that your executing code is operating on a local temp dir, not a
    directory managed by the Django Storage API.
    """
    return shutil.rmtree(path)


def timestamp_index(index):
    """Returns index-YYYYMMDDHHMMSS with the current time."""
    return '%s-%s' % (index, datetime.datetime.now().strftime('%Y%m%d%H%M%S'))


def cached_property(*args, **kw):
    # Handles invocation as a direct decorator or
    # with intermediate keyword arguments.
    if args:  # @cached_property
        return CachedProperty(args[0])
    else:     # @cached_property(name=..., writable=...)
        return lambda f: CachedProperty(f, **kw)


class CachedProperty(object):
    """
    A decorator that converts a function into a lazy property.  The
    function wrapped is called the first time to retrieve the result
    and than that calculated result is used the next time you access
    the value::

        class Foo(object):

            @cached_property
            def foo(self):
                # calculate something important here
                return 42

    Lifted from werkzeug.
    """

    def __init__(self, func, name=None, doc=None, writable=False):
        self.func = func
        self.writable = writable
        self.__name__ = name or func.__name__
        self.__doc__ = doc or func.__doc__

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        _missing = object()
        value = obj.__dict__.get(self.__name__, _missing)
        if value is _missing:
            value = self.func(obj)
            obj.__dict__[self.__name__] = value
        return value

    def __set__(self, obj, value):
        if not self.writable:
            raise TypeError('read only attribute')
        obj.__dict__[self.__name__] = value

    def __delete__(self, obj):
        if not self.writable:
            raise TypeError('read only attribute')
        del obj.__dict__[self.__name__]


def _get_created(created):
    """
    Returns a datetime.

    If `created` is "now", it returns `datetime.datetime.now()`. If `created`
    is set use that. Otherwise generate a random datetime in the year 2011.
    """
    if created == 'now':
        return datetime.datetime.now()
    elif created:
        return created
    else:
        return datetime.datetime(
            2011,
            random.randint(1, 12),  # Month
            random.randint(1, 28),  # Day
            random.randint(0, 23),  # Hour
            random.randint(0, 59),  # Minute
            random.randint(0, 59))  # Seconds


def app_factory(status=mkt.STATUS_PUBLIC, version_kw={}, file_kw={}, **kw):
    """
    Create an app.

    complete -- fills out app details + creates content ratings.
    rated -- creates content ratings

    """
    from mkt.webapps.models import update_search_index, Webapp
    # Disconnect signals until the last save.
    post_save.disconnect(update_search_index, sender=Webapp,
                         dispatch_uid='webapp.search.index')

    complete = kw.pop('complete', False)
    rated = kw.pop('rated', False)
    if complete:
        kw.setdefault('support_email', 'support@example.com')
    when = _get_created(kw.pop('created', None))

    # Keep as much unique data as possible in the uuid: '-' aren't important.
    name = kw.pop('name',
                  u'Webapp %s' % unicode(uuid.uuid4()).replace('-', ''))

    kwargs = {
        # Set artificially the status to STATUS_PUBLIC for now, the real
        # status will be set a few lines below, after the update_version()
        # call. This prevents issues when calling app_factory with
        # STATUS_DELETED.
        'status': mkt.STATUS_PUBLIC,
        'name': name,
        'app_slug': name.replace(' ', '-').lower()[:30],
        'bayesian_rating': random.uniform(1, 5),
        'created': when,
        'last_updated': when,
    }
    kwargs.update(kw)

    # Save 1.
    app = Webapp.objects.create(**kwargs)
    version = version_factory(file_kw, addon=app, **version_kw)  # Save 2.
    app.status = status
    app.update_version()

    # Put signals back.
    post_save.connect(update_search_index, sender=Webapp,
                      dispatch_uid='webapp.search.index')

    app.save()  # Save 4.

    if 'nomination' in version_kw:
        # If a nomination date was set on the version, then it might have been
        # erased at post_save by addons.models.watch_status() or
        # mkt.webapps.models.watch_status().
        version.update(nomination=version_kw['nomination'])

    if rated or complete:
        make_rated(app)

    if complete:
        if not app.categories:
            app.update(categories=['utilities'])
        app.addondevicetype_set.create(device_type=DEVICE_TYPES.keys()[0])
        app.previews.create()

    return app


def extension_factory(status=mkt.STATUS_PUBLIC, **kw):
    from mkt.extensions.models import Extension
    name = kw.get('name',
                  u'Extension %s' % unicode(uuid.uuid4()).replace('-', ''))
    if 'name' in kw:
        del kw['name']

    extension = Extension.objects.create(
        name=name, slug=name.replace(' ', '-').lower()[:30], **kw)
    extension.versions.create(status=status, version='0.1')
    return extension


def file_factory(**kw):
    from mkt.files.models import File
    v = kw['version']
    status = kw.pop('status', mkt.STATUS_PUBLIC)
    f = File.objects.create(filename='%s-%s' % (v.addon_id, v.id),
                            status=status, **kw)
    return f


def website_factory(**kw):
    from mkt.websites.models import Website

    name = kw.pop('name',
                  u'Website %s' % unicode(uuid.uuid4()).replace('-', ''))
    when = _get_created(kw.pop('created', None))

    kwargs = {
        'name': name,
        'short_name': name[0:10],
        'created': when,
        'last_updated': when,
        'url': 'ngokevin.com',
    }
    kwargs.update(kw)

    return Website.objects.create(**kwargs)


def version_factory(file_kw={}, **kw):
    from mkt.versions.models import Version
    version = kw.pop('version', '%.1f' % random.uniform(0, 2))
    v = Version.objects.create(version=version, **kw)
    v.created = v.last_updated = _get_created(kw.pop('created', 'now'))
    v.save()
    file_factory(version=v, **file_kw)
    return v


def make_game(app, rated):
    app.update(categories=['games'])
    if rated:
        make_rated(app)
    app = app.reload()
    return app


def make_rated(app):
    app.set_content_ratings(
        dict((body, body.ratings[0]) for body in
             mkt.ratingsbodies.ALL_RATINGS_BODIES))
    app.set_iarc_info(123, 'abc')
    app.set_descriptors([])
    app.set_interactives([])


def get_icon_url(base_url_format, obj, size,
                 default_format='default-{size}.png'):
    """
    Returns either the icon URL for a given (`obj`, `size`). base_url_format`
    is a string that will be used for url formatting if we are not using a
    remote storage, see ADDON_ICON_URL for an example.

    If no icon type if set on the `obj`, then the url for the
    appropriate default icon for the given `size` will be returned.

    `obj` needs to implement `icon_type` and `icon_hash` properties for this
    function to work.

    Note: does not check size, so it can return 404 URLs if you specify an
    invalid size.
    """
    # Return default image if no icon_type was stored.
    if not obj.icon_type:
        return '{path}/{name}'.format(path=static_url('ICONS_DEFAULT_URL'),
                                      name=default_format.format(size=size))
    else:
        # If we don't have the icon_hash set to a dummy string ("never"),
        # when the icon is eventually changed, icon_hash will be updated.
        suffix = obj.icon_hash or 'never'

        if storage_is_remote():
            # We don't care about base_url_format, the storage provides the url
            # for a given path. We assume AWS_QUERYSTRING_AUTH is False atm.
            path = '%s/%s-%s.png' % (obj.get_icon_dir(), obj.pk, size)
            return '%s?modified=%s' % (public_storage.url(path), suffix)

        # [1] is the whole ID, [2] is the directory.
        split_id = re.match(r'((\d*?)\d{1,3})$', str(obj.pk))
        return base_url_format % (split_id.group(2) or 0, obj.pk, size, suffix)


def get_promo_img_url(base_url_format, obj, size,
                      default_format='default-{size}.png'):
    """
    Returns either the promo img URL for a given (`obj`, `size`).
    base_url_format` is a string that will be used for url formatting, see
    WEBAPP_PROMO_IMG_URL for an example.

    If no promo img type if set on the `obj`, then the url for the
    appropriate default icon for the given `size` will be returned.

    `obj` needs to implement `promo_img_hash` properties for this function to
    work.
    """
    # [1] is the whole ID, [2] is the directory.
    split_id = re.match(r'((\d*?)\d{1,3})$', str(obj.pk))
    # If we don't have the promo_img_hash set to a dummy string ("never"),
    # when the promo_img is eventually changed, promo_img_hash will be updated.
    suffix = obj.promo_img_hash or 'never'
    return base_url_format % (split_id.group(2) or 0, obj.pk, size, suffix)
