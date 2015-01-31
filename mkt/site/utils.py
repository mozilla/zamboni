import codecs
import datetime
import errno
import itertools
import operator
import os
import re
import shutil
import time
import unicodedata
import urllib
import urlparse

from django import http
from django.conf import settings
from django.core import paginator
from django.core.cache import cache
from django.core.files.storage import default_storage as storage
from django.core.files.storage import FileSystemStorage
from django.core.serializers import json
from django.core.urlresolvers import reverse
from django.core.validators import validate_slug, ValidationError
from django.http import HttpRequest
from django.utils.encoding import smart_str, smart_unicode
from django.utils.functional import Promise
from django.utils.http import urlquote

import bleach
import chardet
import commonware.log
import jinja2
import pytz
from caching.base import CachingQuerySet
from cef import log_cef as _log_cef
from easy_thumbnails import processors
from elasticsearch_dsl.search import Search
from PIL import Image, ImageFile, PngImagePlugin

import mkt
from mkt.api.paginator import ESPaginator
from mkt.translations.models import Translation


days_ago = lambda n: datetime.datetime.now() - datetime.timedelta(days=n)

log = commonware.log.getLogger('z.mkt')


def urlparams(url_, hash=None, **query):
    """
    Add a fragment and/or query paramaters to a URL.

    New query params will be appended to exising parameters, except duplicate
    names, which will be replaced.
    """
    url = urlparse.urlparse(url_)
    fragment = hash if hash is not None else url.fragment

    # Use dict(parse_qsl) so we don't get lists of values.
    q = url.query
    query_dict = dict(urlparse.parse_qsl(smart_str(q))) if q else {}
    query_dict.update((k, v) for k, v in query.items())

    query_string = _urlencode([(k, v) for k, v in query_dict.items()
                              if v is not None])
    new = urlparse.ParseResult(url.scheme, url.netloc, url.path, url.params,
                               query_string, fragment)
    return new.geturl()


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


# From: http://bit.ly/eTqloE
# Without this, you'll notice a slight grey line on the edges of
# the adblock plus icon.
def patched_chunk_tRNS(self, pos, len):
    i16 = PngImagePlugin.i16
    s = ImageFile._safe_read(self.fp, len)
    if self.im_mode == "P":
        self.im_info["transparency"] = map(ord, s)
    elif self.im_mode == "L":
        self.im_info["transparency"] = i16(s)
    elif self.im_mode == "RGB":
        self.im_info["transparency"] = i16(s), i16(s[2:]), i16(s[4:])
    return s
PngImagePlugin.PngStream.chunk_tRNS = patched_chunk_tRNS


def patched_load(self):
    if self.im and self.palette and self.palette.dirty:
        apply(self.im.putpalette, self.palette.getdata())
        self.palette.dirty = 0
        self.palette.rawmode = None
        try:
            trans = self.info["transparency"]
        except KeyError:
            self.palette.mode = "RGB"
        else:
            try:
                for i, a in enumerate(trans):
                    self.im.putpalettealpha(i, a)
            except TypeError:
                self.im.putpalettealpha(trans, 0)
            self.palette.mode = "RGBA"
    if self.im:
        return self.im.pixel_access(self.readonly)
Image.Image.load = patched_load


def resize_image(src, dst, size=None, remove_src=True, locally=False):
    """Resizes and image from src, to dst. Returns width and height.

    When locally is True, src and dst are assumed to reside
    on the local disk (not in the default storage). When dealing
    with local files it's up to you to ensure that all directories
    exist leading up to the dst filename.
    """
    if src == dst:
        raise Exception("src and dst can't be the same: %s" % src)

    open_ = open if locally else storage.open
    delete = os.unlink if locally else storage.delete

    with open_(src, 'rb') as fp:
        im = Image.open(fp)
        im = im.convert('RGBA')
        if size:
            im = processors.scale_and_crop(im, size)
    with open_(dst, 'wb') as fp:
        im.save(fp, 'png')

    if remove_src:
        delete(src)

    return im.size


def remove_icons(destination):
    for size in mkt.APP_ICON_SIZES:
        filename = '%s-%s.png' % (destination, size)
        if storage.exists(filename):
            storage.delete(filename)


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
            # See the PIL docs for how this works:
            # http://www.pythonware.com/library/pil/handbook/introduction.htm
            try:
                img.seek(1)
            except EOFError:
                return False
            return True


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
        fp = open(self.path, 'rb')
        if 'wsgi.file_wrapper' in self.request.META:
            return self.request.META['wsgi.file_wrapper'](fp, chunk)
        else:
            self['Content-Length'] = os.path.getsize(self.path)

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


class LocalFileStorage(FileSystemStorage):
    """Local storage to an unregulated absolute file path.

    Unregulated means that, unlike the default file storage, you can write to
    any path on the system if you have access.

    Unlike Django's default FileSystemStorage, this class behaves more like a
    "cloud" storage system. Specifically, you never have to write defensive
    code that prepares for leading directory paths to exist.
    """

    def __init__(self, base_url=None):
        super(LocalFileStorage, self).__init__(location='/', base_url=base_url)

    def delete(self, name):
        """Delete a file or empty directory path.

        Unlike the default file system storage this will also delete an empty
        directory path. This behavior is more in line with other storage
        systems like S3.
        """
        full_path = self.path(name)
        if os.path.isdir(full_path):
            os.rmdir(full_path)
        else:
            return super(LocalFileStorage, self).delete(name)

    def _open(self, name, mode='rb'):
        if mode.startswith('w'):
            parent = os.path.dirname(self.path(name))
            try:
                # Try/except to prevent race condition raising "File exists".
                os.makedirs(parent)
            except OSError as e:
                if e.errno == errno.EEXIST and os.path.isdir(parent):
                    pass
                else:
                    raise
        return super(LocalFileStorage, self)._open(name, mode=mode)

    def path(self, name):
        """Actual file system path to name without any safety checks."""
        return os.path.normpath(os.path.join(self.location,
                                             self._smart_path(name)))

    def _smart_path(self, string):
        if os.path.supports_unicode_filenames:
            return smart_unicode(string)
        return smart_str(string)


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


def walkfiles(folder, suffix=''):
    """Iterator over files in folder, recursively."""
    return (os.path.join(basename, filename)
            for basename, dirnames, filenames in os.walk(folder)
            for filename in filenames
            if filename.endswith(suffix))


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
            if isinstance(value, CachingQuerySet):
                # Work around a bug in django-cache-machine that
                # causes deadlock or infinite recursion if
                # CachingQuerySets are cached before they run their
                # query.
                value._fetch_all()
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
