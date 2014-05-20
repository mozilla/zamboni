import functools

from django import http
from django.shortcuts import (get_list_or_404, get_object_or_404, redirect,
                              render)
from django.views.decorators.vary import vary_on_headers

import commonware.log
import session_csrf
from mobility.decorators import mobilized
from tower import ugettext as _, ugettext_lazy as _lazy

import amo
from abuse.models import send_abuse_report
from amo import messages, urlresolvers
from amo.forms import AbuseForm
from amo.models import manual_order
from amo.urlresolvers import reverse
from reviews.models import Review
from translations.query import order_by_translation
from versions.models import Version

from .decorators import addon_view_factory
from .models import Addon


log = commonware.log.getLogger('z.addons')
addon_view = addon_view_factory(qs=Addon.objects.valid)
addon_unreviewed_view = addon_view_factory(qs=Addon.objects.unreviewed)
addon_disabled_view = addon_view_factory(qs=Addon.objects.valid_and_disabled)


def author_addon_clicked(f):
    """Decorator redirecting clicks on "Other add-ons by author"."""
    @functools.wraps(f)
    def decorated(request, *args, **kwargs):
        redirect_id = request.GET.get('addons-author-addons-select', None)
        if not redirect_id:
            return f(request, *args, **kwargs)
        try:
            target_id = int(redirect_id)
            return http.HttpResponsePermanentRedirect(reverse(
                'addons.detail', args=[target_id]))
        except ValueError:
            return http.HttpResponseBadRequest('Invalid add-on ID.')
    return decorated


@addon_disabled_view
def addon_detail(request, addon):
    """Add-ons details page dispatcher."""
    if addon.is_deleted:
        raise http.Http404
    if addon.is_disabled:
        return render(request, 'addons/impala/disabled.html',
                      {'addon': addon}, status=404)
    if addon.is_webapp():
        # Apps don't deserve AMO detail pages.
        raise http.Http404

    # addon needs to have a version and be valid for this app.
    if addon.type in request.APP.types:
        if not addon.current_version:
            raise http.Http404

        return extension_detail(request, addon)
    else:
        # Redirect to an app that supports this type.
        try:
            new_app = [a for a in amo.APP_USAGE if addon.type
                       in a.types][0]
        except IndexError:
            raise http.Http404
        else:
            prefixer = urlresolvers.get_url_prefix()
            prefixer.app = new_app.short
            return http.HttpResponsePermanentRedirect(reverse(
                'addons.detail', args=[addon.slug]))


@vary_on_headers('X-Requested-With')
def extension_detail(request, addon):
    """Extensions details page."""
    # If current version is incompatible with this app, redirect.
    comp_apps = addon.compatible_apps
    if comp_apps and request.APP not in comp_apps:
        prefixer = urlresolvers.get_url_prefix()
        prefixer.app = comp_apps.keys()[0].short
        return redirect('addons.detail', addon.slug, permanent=True)

    # Addon recommendations.
    recommended = Addon.objects.listed(request.APP).filter(
        recommended_for__addon=addon)[:6]

    ctx = {
        'addon': addon,
        'src': request.GET.get('src', 'dp-btn-primary'),
        'version_src': request.GET.get('src', 'dp-btn-version'),
        'tags': addon.tags.not_blacklisted(),
        'recommendations': recommended,
        'reviews': Review.objects.valid().filter(addon=addon, is_latest=True),
        'get_replies': Review.get_replies,
        'abuse_form': AbuseForm(request=request),
    }

    # details.html just returns the top half of the page for speed. The bottom
    # does a lot more queries we don't want on the initial page load.
    if request.is_ajax():
        # Other add-ons/apps from the same author(s).
        ctx['author_addons'] = addon.authors_other_addons(app=request.APP)[:6]
        return render(request, 'addons/impala/details-more.html', ctx)
    else:
        if addon.is_webapp():
            ctx['search_placeholder'] = 'apps'
        return render(request, 'addons/impala/details.html', ctx)


@mobilized(extension_detail)
def extension_detail(request, addon):
    return render(request, 'addons/mobile/details.html', {'addon': addon})


class BaseFilter(object):
    """
    Filters help generate querysets for add-on listings.

    You have to define ``opts`` on the subclass as a sequence of (key, title)
    pairs.  The key is used in GET parameters and the title can be used in the
    view.

    The chosen filter field is combined with the ``base`` queryset using
    the ``key`` found in request.GET.  ``default`` should be a key in ``opts``
    that's used if nothing good is found in request.GET.
    """

    def __init__(self, request, base, key, default, model=Addon):
        self.opts_dict = dict(self.opts)
        self.extras_dict = dict(self.extras) if hasattr(self, 'extras') else {}
        self.request = request
        self.base_queryset = base
        self.key = key
        self.model = model
        self.field, self.title = self.options(self.request, key, default)
        self.qs = self.filter(self.field)

    def options(self, request, key, default):
        """Get the (option, title) pair we want according to the request."""
        if key in request.GET and (request.GET[key] in self.opts_dict or
                                   request.GET[key] in self.extras_dict):
            opt = request.GET[key]
        else:
            opt = default
        if opt in self.opts_dict:
            title = self.opts_dict[opt]
        else:
            title = self.extras_dict[opt]
        return opt, title

    def all(self):
        """Get a full mapping of {option: queryset}."""
        return dict((field, self.filter(field)) for field in dict(self.opts))

    def filter(self, field):
        """Get the queryset for the given field."""
        filter = self._filter(field) & self.base_queryset
        order = getattr(self, 'order_%s' % field, None)
        if order:
            return order(filter)
        return filter

    def _filter(self, field):
        return getattr(self, 'filter_%s' % field)()

    def filter_featured(self):
        ids = self.model.featured_random(self.request.APP, self.request.LANG)
        return manual_order(self.model.objects, ids, 'addons.id')

    def filter_price(self):
        return self.model.objects.order_by('addonpremium__price__price', 'id')

    def filter_free(self):
        if self.model == Addon:
            return self.model.objects.top_free(self.request.APP, listed=False)
        else:
            return self.model.objects.top_free(listed=False)

    def filter_paid(self):
        if self.model == Addon:
            return self.model.objects.top_paid(self.request.APP, listed=False)
        else:
            return self.model.objects.top_paid(listed=False)

    def filter_popular(self):
        return (self.model.objects.order_by('-weekly_downloads')
                .with_index(addons='downloads_type_idx'))

    def filter_downloads(self):
        return self.filter_popular()

    def filter_users(self):
        return (self.model.objects.order_by('-average_daily_users')
                .with_index(addons='adus_type_idx'))

    def filter_created(self):
        return (self.model.objects.order_by('-created')
                .with_index(addons='created_type_idx'))

    def filter_updated(self):
        return (self.model.objects.order_by('-last_updated')
                .with_index(addons='last_updated_type_idx'))

    def filter_rating(self):
        return (self.model.objects.order_by('-bayesian_rating')
                .with_index(addons='rating_type_idx'))

    def filter_hotness(self):
        return self.model.objects.order_by('-hotness')

    def filter_name(self):
        return order_by_translation(self.model.objects.all(), 'name')


class ESBaseFilter(BaseFilter):
    """BaseFilter that uses elasticsearch."""

    def __init__(self, request, base, key, default):
        super(ESBaseFilter, self).__init__(request, base, key, default)

    def filter(self, field):
        sorts = {'name': 'name_sort',
                 'created': '-created',
                 'updated': '-last_updated',
                 'popular': '-weekly_downloads',
                 'users': '-average_daily_users',
                 'rating': '-bayesian_rating'}
        return self.base_queryset.order_by(sorts[field])


class HomepageFilter(BaseFilter):
    opts = (('featured', _lazy(u'Featured')),
            ('popular', _lazy(u'Popular')),
            ('new', _lazy(u'Recently Added')),
            ('updated', _lazy(u'Recently Updated')))

    filter_new = BaseFilter.filter_created


# Define a placeholder home response until we can hunt down all the places
# it is called from and remove them.
def home(request):
    return http.HttpResponse('home')


@addon_view
def eula(request, addon, file_id=None):
    if not addon.eula:
        return http.HttpResponseRedirect(addon.get_url_path())
    if file_id:
        version = get_object_or_404(addon.versions, files__id=file_id)
    else:
        version = addon.current_version
    return render(request, 'addons/eula.html',
                  {'addon': addon, 'version': version})


@addon_view
def privacy(request, addon):
    if not addon.privacy_policy:
        return http.HttpResponseRedirect(addon.get_url_path())

    return render(request, 'addons/privacy.html', {'addon': addon})


@addon_view
def developers(request, addon, page):
    if 'version' in request.GET:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=request.GET['version'])[0]
    else:
        version = addon.current_version

    if 'src' in request.GET:
        contribution_src = src = request.GET['src']
    else:
        page_srcs = {
            'developers': ('developers', 'meet-developers'),
            'installed': ('meet-the-developer-post-install', 'post-download'),
            'roadblock': ('meetthedeveloper_roadblock', 'roadblock'),
        }
        # Download src and contribution_src are different.
        src, contribution_src = page_srcs.get(page)
    return render(request, 'addons/impala/developers.html',
                  {'addon': addon, 'page': page, 'src': src,
                   'contribution_src': contribution_src,
                   'version': version})


@addon_view
def license(request, addon, version=None):
    if version is not None:
        qs = addon.versions.filter(files__status__in=amo.VALID_STATUSES)
        version = get_list_or_404(qs, version=version)[0]
    else:
        version = addon.current_version
    if not (version and version.license):
        raise http.Http404
    return render(request, 'addons/impala/license.html',
                  dict(addon=addon, version=version))


def license_redirect(request, version):
    version = get_object_or_404(Version, pk=version)
    return redirect(version.license_url(), permanent=True)


@session_csrf.anonymous_csrf_exempt
@addon_view
def report_abuse(request, addon):
    form = AbuseForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        send_abuse_report(request, addon, form.cleaned_data['text'])
        messages.success(request, _('Abuse reported.'))
        return http.HttpResponseRedirect(addon.get_url_path())
    else:
        return render(request, 'addons/report_abuse_full.html',
                      {'addon': addon, 'abuse_form': form})
