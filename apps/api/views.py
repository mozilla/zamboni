"""
API views
"""
import itertools
import json
import random
from datetime import date, timedelta

from django.http import HttpResponse
from django.template.context import get_standard_processors
from django.utils import encoding, translation

import commonware.log
import jingo
from caching.base import cached_with
from tower import ugettext as _, ugettext_lazy

import amo
import api
from addons.models import Addon
from amo.models import manual_order
from amo.utils import JSONEncoder
from api.utils import addon_to_dict
from versions.compare import version_int


ERROR = 'error'
OUT_OF_DATE = ugettext_lazy(
    u"The API version, {0:.1f}, you are using is not valid.  "
    u"Please upgrade to the current version {1:.1f} API.")

xml_env = jingo.env.overlay()
old_finalize = xml_env.finalize
xml_env.finalize = lambda x: amo.helpers.strip_controls(old_finalize(x))


# Hard limit of 30.  The buffer is to try for locale-specific add-ons.
MAX_LIMIT, BUFFER = 30, 10

# "New" is arbitrarily defined as 10 days old.
NEW_DAYS = 10

log = commonware.log.getLogger('z.api')


# TODO: Remove code below along with /apps/discovery.

def render_xml_to_string(request, template, context={}):
    if not jingo._helpers_loaded:
        jingo.load_helpers()

    for processor in get_standard_processors():
        context.update(processor(request))

    template = xml_env.get_template(template)
    return template.render(context)


def render_xml(request, template, context={}, **kwargs):
    """Safely renders xml, stripping out nasty control characters."""
    rendered = render_xml_to_string(request, template, context)

    if 'mimetype' not in kwargs:
        kwargs['mimetype'] = 'text/xml'

    return HttpResponse(rendered, **kwargs)


def partition(seq, key):
    """Group a sequence based into buckets by key(x)."""
    groups = itertools.groupby(sorted(seq, key=key), key=key)
    return ((k, list(v)) for k, v in groups)


def addon_filter(addons, addon_type, limit, app, platform, version,
                 compat_mode='strict', shuffle=True):
    """
    Filter addons by type, application, app version, and platform.

    Add-ons that support the current locale will be sorted to front of list.
    Shuffling will be applied to the add-ons supporting the locale and the
    others separately.

    Doing this in the database takes too long, so we in code and wrap it in
    generous caching.
    """
    APP = app

    if addon_type.upper() != 'ALL':
        try:
            addon_type = int(addon_type)
            if addon_type:
                addons = [a for a in addons if a.type == addon_type]
        except ValueError:
            # `addon_type` is ALL or a type id.  Otherwise we ignore it.
            pass

    # Take out personas since they don't have versions.
    groups = dict(partition(addons,
                            lambda x: x.type == amo.ADDON_PERSONA))
    personas, addons = groups.get(True, []), groups.get(False, [])

    platform = platform.lower()
    if platform != 'all' and platform in amo.PLATFORM_DICT:
        pid = amo.PLATFORM_DICT[platform]
        f = lambda ps: pid in ps or amo.PLATFORM_ALL in ps
        addons = [a for a in addons
                  if f(a.current_version.supported_platforms)]

    if version is not None:
        vint = version_int(version)
        f_strict = lambda app: (app.min.version_int <= vint
                                                    <= app.max.version_int)
        f_ignore = lambda app: app.min.version_int <= vint
        xs = [(a, a.compatible_apps) for a in addons]

        # Iterate over addons, checking compatibility depending on compat_mode.
        addons = []
        for addon, apps in xs:
            app = apps.get(APP)
            if compat_mode == 'strict':
                if app and f_strict(app):
                    addons.append(addon)
            elif compat_mode == 'ignore':
                if app and f_ignore(app):
                    addons.append(addon)
            elif compat_mode == 'normal':
                # This does a db hit but it's cached. This handles the cases
                # for strict opt-in, binary components, and compat overrides.
                v = addon.compatible_version(APP.id, version, platform,
                                             compat_mode)
                if v:  # There's a compatible version.
                    addons.append(addon)

    # Put personas back in.
    addons.extend(personas)

    # We prefer add-ons that support the current locale.
    lang = translation.get_language()
    partitioner = lambda x: (x.description is not None and
                             (x.description.locale == lang))
    groups = dict(partition(addons, partitioner))
    good, others = groups.get(True, []), groups.get(False, [])

    if shuffle:
        random.shuffle(good)
        random.shuffle(others)

    # If limit=0, we return all addons with `good` coming before `others`.
    # Otherwise pad `good` if less than the limit and return the limit.
    if limit > 0:
        if len(good) < limit:
            good.extend(others[:limit - len(good)])
        return good[:limit]
    else:
        good.extend(others)
        return good


def validate_api_version(version):
    """
    We want to be able to deprecate old versions of the API, therefore we check
    for a minimum API version before continuing.
    """
    if float(version) < api.MIN_VERSION:
        return False

    if float(version) > api.MAX_VERSION:
        return False

    return True


class APIView(object):
    """
    Base view class for all API views.
    """

    def __call__(self, request, api_version, *args, **kwargs):

        self.version = float(api_version)
        self.format = request.REQUEST.get('format', 'xml')
        self.mimetype = ('text/xml' if self.format == 'xml'
                         else 'application/json')
        self.request = request
        if not validate_api_version(api_version):
            msg = OUT_OF_DATE.format(self.version, api.CURRENT_VERSION)
            return self.render_msg(msg, ERROR, status=403,
                                   mimetype=self.mimetype)

        return self.process_request(*args, **kwargs)

    def render_msg(self, msg, error_level=None, *args, **kwargs):
        """
        Renders a simple message.
        """

        if self.format == 'xml':
            return render_xml(self.request, 'api/message.xml',
                {'error_level': error_level, 'msg': msg}, *args, **kwargs)
        else:
            return HttpResponse(json.dumps({'msg': _(msg)}), *args, **kwargs)

    def render(self, template, context):
        context['api_version'] = self.version
        context['api'] = api

        if self.format == 'xml':
            return render_xml(self.request, template, context,
                              mimetype=self.mimetype)
        else:
            return HttpResponse(self.render_json(context),
                                mimetype=self.mimetype)

    def render_json(self, context):
        return json.dumps({'msg': _('Not implemented yet.')})


class ListView(APIView):

    def process_request(self, list_type='recommended', addon_type='ALL',
                        limit=10, platform='ALL', version=None,
                        compat_mode='strict'):
        """
        Find a list of new or featured add-ons.  Filtering is done in Python
        for cache-friendliness and to avoid heavy queries.
        """
        limit = min(MAX_LIMIT, int(limit))
        APP, platform = self.request.APP, platform.lower()
        qs = Addon.objects.listed(APP).exclude(type=amo.ADDON_WEBAPP)
        shuffle = True

        if list_type in ('by_adu', 'featured'):
            qs = qs.exclude(type=amo.ADDON_PERSONA)

        if list_type == 'newest':
            new = date.today() - timedelta(days=NEW_DAYS)
            addons = (qs.filter(created__gte=new)
                      .order_by('-created'))[:limit + BUFFER]
        elif list_type == 'by_adu':
            addons = qs.order_by('-average_daily_users')[:limit + BUFFER]
            shuffle = False  # By_adu is an ordered list.
        elif list_type == 'hotness':
            # Filter to type=1 so we hit visible_idx. Only extensions have a
            # hotness index right now so this is not incorrect.
            addons = (qs.filter(type=amo.ADDON_EXTENSION)
                      .order_by('-hotness'))[:limit + BUFFER]
            shuffle = False
        else:
            ids = Addon.featured_random(APP, self.request.LANG)
            addons = manual_order(qs, ids[:limit + BUFFER], 'addons.id')
            shuffle = False

        args = (addon_type, limit, APP, platform, version, compat_mode,
                shuffle)
        f = lambda: self._process(addons, *args)
        return cached_with(addons, f, map(encoding.smart_str, args))

    def _process(self, addons, *args):
        return self.render('api/list.xml',
                           {'addons': addon_filter(addons, *args)})

    def render_json(self, context):
        return json.dumps([addon_to_dict(a) for a in context['addons']],
                          cls=JSONEncoder)
