import collections
import datetime
import functools
import HTMLParser
import json
import os
import sys
import traceback
import urllib

from django import http
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

import commonware.log
import jinja2
import requests
import waffle
from appvalidator.constants import PERMISSIONS
from cache_nuggets.lib import Token
from jingo.helpers import urlparams
from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.generics import (CreateAPIView, ListAPIView, UpdateAPIView,
                                     DestroyAPIView)
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from tower import ugettext as _
from waffle.decorators import waffle_switch

import mkt
from lib.crypto.packaged import SigningError
from mkt.abuse.forms import AbuseViewFormSet
from mkt.abuse.models import AbuseReport
from mkt.access import acl
from mkt.api.authentication import (RestOAuthAuthentication,
                                    RestSharedSecretAuthentication)
from mkt.api.authorization import AnyOf, ByHttpMethod, GroupPermission
from mkt.api.base import CORSMixin, MarketplaceView, SlugOrIdMixin
from mkt.comm.forms import CommAttachmentFormSet
from mkt.constants import MANIFEST_CONTENT_TYPE
from mkt.developers.models import ActivityLog, ActivityLogAttachment
from mkt.ratings.forms import ReviewFlagFormSet
from mkt.ratings.models import Review, ReviewFlag
from mkt.regions.utils import parse_region
from mkt.reviewers.forms import (ApiReviewersSearchForm, ApproveRegionForm,
                                 ModerateLogDetailForm, ModerateLogForm,
                                 MOTDForm)
from mkt.reviewers.models import (AdditionalReview, CannedResponse,
                                  EditorSubscription, QUEUE_TARAKO,
                                  ReviewerScore)
from mkt.reviewers.serializers import (AdditionalReviewSerializer,
                                       CannedResponseSerializer,
                                       ReviewerAdditionalReviewSerializer,
                                       ReviewerScoreSerializer,
                                       ReviewersESAppSerializer,
                                       ReviewingSerializer)
from mkt.reviewers.utils import (AppsReviewing, log_reviewer_action,
                                 ReviewApp, ReviewersQueuesHelper)
from mkt.search.filters import (ReviewerSearchFormFilter, SearchQueryFilter,
                                SortingFilter)
from mkt.search.views import SearchView
from mkt.site.decorators import json_view, login_required, permission_required
from mkt.site.helpers import absolutify, product_as_dict
from mkt.site.utils import (days_ago, escape_all, HttpResponseSendFile,
                            JSONEncoder, paginate, redirect_for_login,
                            smart_decode)
from mkt.submit.forms import AppFeaturesForm
from mkt.tags.models import Tag
from mkt.users.models import UserProfile
from mkt.webapps.decorators import app_view, app_view_factory
from mkt.webapps.models import AddonDeviceType, AddonUser, Version, Webapp
from mkt.webapps.signals import version_changed
from mkt.websites.models import Website
from mkt.zadmin.models import set_config, unmemoized_get_config

from . import forms


QUEUE_PER_PAGE = 100
log = commonware.log.getLogger('z.reviewers')
app_view_with_deleted = app_view_factory(Webapp.with_deleted.all)


def reviewer_required(region=None, moderator=False):
    """Requires the user to be logged in as a reviewer or admin, or allows
    someone with rule 'ReviewerTools:View' for GET requests.

    Reviewer is someone who is in one of the groups with the following
    permissions:

        Apps:Review

    moderator=True extends this to users in groups who have the permssion:

        Apps:ModerateReview

    """
    def decorator(f):
        @login_required
        @functools.wraps(f)
        def wrapper(request, *args, **kw):
            reviewer_perm = acl.check_reviewer(request,
                                               region=kw.get('region'))
            moderator_perm = (moderator and
                              acl.action_allowed(request,
                                                 'Apps', 'ModerateReview'))
            view_only = (request.method == 'GET' and
                         acl.action_allowed(request, 'ReviewerTools', 'View'))
            if (reviewer_perm or moderator_perm or view_only):
                return f(request, *args, **kw)
            else:
                raise PermissionDenied
        return wrapper
    # If decorator has no args, and is "paren-less", it's callable.
    if callable(region):
        return decorator(region)
    else:
        return decorator


@reviewer_required(moderator=True)
def route_reviewer(request):
    """
    Redirect to apps home page if app reviewer.
    """
    return http.HttpResponseRedirect(reverse('reviewers.home'))


@reviewer_required(moderator=True)
def home(request):
    durations = (('new', _('New Apps (Under 5 days)')),
                 ('med', _('Passable (5 to 10 days)')),
                 ('old', _('Overdue (Over 10 days)')))

    progress, percentage = _progress()

    data = context(
        request,
        reviews_total=ActivityLog.objects.total_reviews(webapp=True)[:5],
        reviews_monthly=ActivityLog.objects.monthly_reviews(webapp=True)[:5],
        progress=progress,
        percentage=percentage,
        durations=durations,
        full_reviewer=acl.check_reviewer(request)
    )
    return render(request, 'reviewers/home.html', data)


def queue_counts(request):
    use_es = waffle.switch_is_active('reviewer-tools-elasticsearch')
    queues_helper = ReviewersQueuesHelper(use_es=use_es)

    counts = {
        'pending': queues_helper.get_pending_queue().count(),
        'rereview': queues_helper.get_rereview_queue().count(),
        'updates': queues_helper.get_updates_queue().count(),
        'escalated': queues_helper.get_escalated_queue().count(),
        'moderated': queues_helper.get_moderated_queue().count(),
        'abuse': queues_helper.get_abuse_queue().count(),
        'region_cn': Webapp.objects.pending_in_region(mkt.regions.CHN).count(),
        'additional_tarako': (
            AdditionalReview.objects
                            .unreviewed(queue=QUEUE_TARAKO, and_approved=True)
                            .count()),
    }

    rv = {}
    if isinstance(type, basestring):
        return counts[type]
    for k, v in counts.items():
        if not isinstance(type, list) or k in type:
            rv[k] = v
    return rv


def _progress():
    """Returns unreviewed apps progress.

    Return the number of apps still unreviewed for a given period of time and
    the percentage.
    """

    queues_helper = ReviewersQueuesHelper()

    base_filters = {
        'pending': (queues_helper.get_pending_queue(),
                    'nomination'),
        'rereview': (queues_helper.get_rereview_queue(),
                     'created'),
        'escalated': (queues_helper.get_escalated_queue(),
                      'created'),
        'updates': (queues_helper.get_updates_queue(),
                    'nomination')
    }

    operators_and_values = {
        'new': ('gt', days_ago(5)),
        'med': ('range', (days_ago(10), days_ago(5))),
        'old': ('lt', days_ago(10)),
        'week': ('gte', days_ago(7))
    }

    types = base_filters.keys()
    progress = {}

    for t in types:
        tmp = {}
        base_query, field = base_filters[t]
        for k in operators_and_values.keys():
            operator, value = operators_and_values[k]
            filter_ = {}
            filter_['%s__%s' % (field, operator)] = value
            tmp[k] = base_query.filter(**filter_).count()
        progress[t] = tmp

    def pct(p, t):
        # Return the percent of (p)rogress out of (t)otal.
        return (p / float(t)) * 100 if p > 0 else 0

    percentage = {}
    for t in types:
        total = progress[t]['new'] + progress[t]['med'] + progress[t]['old']
        percentage[t] = {}
        for duration in ('new', 'med', 'old'):
            percentage[t][duration] = pct(progress[t][duration], total)

    return (progress, percentage)


def context(request, **kw):
    statuses = dict((k, unicode(v)) for k, v in mkt.STATUS_CHOICES_API.items())
    ctx = dict(motd=unmemoized_get_config('mkt_reviewers_motd'),
               queue_counts=queue_counts(request),
               search_url=reverse('reviewers-search-api'),
               statuses=statuses, point_types=mkt.REVIEWED_MARKETPLACE)
    ctx.update(kw)
    return ctx


def _review(request, addon, version):

    if (not settings.ALLOW_SELF_REVIEWS and
        not acl.action_allowed(request, 'Admin', '%') and
            addon.has_author(request.user)):
        messages.warning(request, _('Self-reviews are not allowed.'))
        return redirect(reverse('reviewers.home'))

    if (addon.status == mkt.STATUS_BLOCKED and
            not acl.action_allowed(request, 'Apps', 'ReviewEscalated')):
        messages.warning(
            request, _('Only senior reviewers can review blocklisted apps.'))
        return redirect(reverse('reviewers.home'))

    attachment_formset = CommAttachmentFormSet(data=request.POST or None,
                                               files=request.FILES or None,
                                               prefix='attachment')
    form = forms.get_review_form(data=request.POST or None,
                                 files=request.FILES or None, request=request,
                                 addon=addon, version=version,
                                 attachment_formset=attachment_formset)
    postdata = request.POST if request.method == 'POST' else None
    all_forms = [form, attachment_formset]

    if version:
        features_list = [unicode(f) for f in version.features.to_list()]
        appfeatures_form = AppFeaturesForm(data=postdata,
                                           instance=version.features)
        all_forms.append(appfeatures_form)
    else:
        appfeatures_form = None
        features_list = None

    queue_type = form.helper.review_type
    redirect_url = reverse('reviewers.apps.queue_%s' % queue_type)
    is_admin = acl.action_allowed(request, 'Apps', 'Edit')

    if request.method == 'POST' and all(f.is_valid() for f in all_forms):
        if form.cleaned_data.get('action') == 'public':
            old_types = set(o.id for o in addon.device_types)
            new_types = set(form.cleaned_data.get('device_override'))

            old_features = set(features_list)
            new_features = set(unicode(f) for f
                               in appfeatures_form.instance.to_list())

            if old_types != new_types:
                # The reviewer overrode the device types. We need to not
                # publish this app immediately.
                if addon.publish_type == mkt.PUBLISH_IMMEDIATE:
                    addon.update(publish_type=mkt.PUBLISH_PRIVATE)

                # And update the device types to what the reviewer set.
                AddonDeviceType.objects.filter(addon=addon).delete()
                for device in form.cleaned_data.get('device_override'):
                    addon.addondevicetype_set.create(device_type=device)

                # Log that the reviewer changed the device types.
                added_devices = new_types - old_types
                removed_devices = old_types - new_types
                msg_list = [
                    _(u'Added {0}').format(unicode(mkt.DEVICE_TYPES[d].name))
                    for d in added_devices
                ] + [
                    _(u'Removed {0}').format(unicode(mkt.DEVICE_TYPES[d].name))
                    for d in removed_devices
                ]
                msg = _(u'Device(s) changed by '
                        u'reviewer: {0}').format(', '.join(msg_list))

                log_reviewer_action(addon, request.user, msg,
                                    mkt.LOG.REVIEW_DEVICE_OVERRIDE)

            if old_features != new_features:
                # The reviewer overrode the requirements. We need to not
                # publish this app immediately.
                if addon.publish_type == mkt.PUBLISH_IMMEDIATE:
                    addon.update(publish_type=mkt.PUBLISH_PRIVATE)

                appfeatures_form.save(mark_for_rereview=False)

                # Log that the reviewer changed the minimum requirements.
                added_features = new_features - old_features
                removed_features = old_features - new_features

                fmt = ', '.join(
                      [_(u'Added {0}').format(f) for f in added_features] +
                      [_(u'Removed {0}').format(f) for f in removed_features])
                # L10n: {0} is the list of requirements changes.
                msg = _(u'Requirements changed by reviewer: {0}').format(fmt)

                log_reviewer_action(addon, request.user, msg,
                                    mkt.LOG.REVIEW_FEATURES_OVERRIDE)

        score = form.helper.process()

        if form.cleaned_data.get('notify'):
            # TODO: bug 741679 for implementing notifications in Marketplace.
            EditorSubscription.objects.get_or_create(user=request.user,
                                                     addon=addon)

        is_tarako = form.cleaned_data.get('is_tarako', False)
        if is_tarako:
            Tag(tag_text='tarako').save_tag(addon)
        else:
            Tag(tag_text='tarako').remove_tag(addon)

        # Success message.
        if score:
            score = ReviewerScore.objects.filter(user=request.user)[0]
            # L10N: {0} is the type of review. {1} is the points they earned.
            #       {2} is the points they now have total.
            success = _(
                u'"{0}" successfully processed (+{1} points, {2} total).'
                .format(unicode(mkt.REVIEWED_CHOICES[score.note_key]),
                        score.score,
                        ReviewerScore.get_total(request.user)))
        else:
            success = _('Review successfully processed.')
        messages.success(request, success)

        return redirect(redirect_url)

    canned = CannedResponse.objects.all()
    actions = form.helper.actions.items()

    try:
        if not version:
            raise Version.DoesNotExist
        show_diff = (addon.versions.exclude(id=version.id)
                                   .filter(files__isnull=False,
                                           created__lt=version.created,
                                           files__status=mkt.STATUS_PUBLIC)
                                   .latest())
    except Version.DoesNotExist:
        show_diff = None

    # The actions we should show a minimal form from.
    actions_minimal = [k for (k, a) in actions if not a.get('minimal')]

    # We only allow the user to check/uncheck files for "pending"
    allow_unchecking_files = form.helper.review_type == "pending"

    versions = (Version.with_deleted.filter(addon=addon)
                                    .order_by('-created')
                                    .transform(Version.transformer_activity)
                                    .transform(Version.transformer))

    product_attrs = {
        'product': json.dumps(
            product_as_dict(request, addon, False, 'reviewer'),
            cls=JSONEncoder),
        'manifest_url': addon.manifest_url,
    }

    pager = paginate(request, versions, 10)

    num_pages = pager.paginator.num_pages
    count = pager.paginator.count

    ctx = context(request, version=version, product=addon, pager=pager,
                  num_pages=num_pages, count=count,
                  form=form, canned=canned, is_admin=is_admin,
                  status_types=mkt.STATUS_CHOICES, show_diff=show_diff,
                  allow_unchecking_files=allow_unchecking_files,
                  actions=actions, actions_minimal=actions_minimal,
                  tab=queue_type, product_attrs=product_attrs,
                  attachment_formset=attachment_formset,
                  appfeatures_form=appfeatures_form)

    if features_list is not None:
        ctx['feature_list'] = features_list

    return render(request, 'reviewers/review.html', ctx)


@reviewer_required
@app_view_with_deleted
def app_review(request, addon):
    version = addon.latest_version
    resp = None
    try:
        with transaction.atomic():
            resp = _review(request, addon, version)
    except SigningError, exc:
        messages.error(request, 'Signing Error: %s' % exc)
        return redirect(
            reverse('reviewers.apps.review', args=[addon.app_slug]))
    # We (hopefully) have been avoiding sending send post_save and
    # version_changed signals in the review process till now (_review()
    # uses ReviewHelper which should have done all of its update() calls
    # with _signal=False).
    #
    # Now is a good time to send them: the transaction we were in has been
    # committed, so we know everything is ok. This is important: we need
    # them to index the app or call update_version() if that wasn't done
    # before already.
    if request.method == 'POST':
        post_save.send(sender=Webapp, instance=addon, created=False)
        post_save.send(sender=Version, instance=version, created=False)
        if getattr(addon, 'resend_version_changed_signal', False):
            version_changed.send(sender=addon)
            del addon.resend_version_changed_signal
    if resp:
        return resp
    raise


QueuedApp = collections.namedtuple('QueuedApp', 'app date_field')
ActionableQueuedApp = collections.namedtuple(
    'QueuedApp', 'app date_field action_url')


def _queue(request, apps, tab, pager_processor=None, date_sort='created',
           template='reviewers/queue.html', data=None, use_es=False):
    per_page = request.GET.get('per_page', QUEUE_PER_PAGE)
    pager = paginate(request, apps, per_page)

    ctx = {
        'addons': pager.object_list,
        'pager': pager,
        'tab': tab,
        'search_form': _get_search_form(request),
        'date_sort': date_sort,
        'use_es': use_es,
    }

    # Additional context variables.
    if data is not None:
        ctx.update(data)

    return render(request, template, context(request, **ctx))


@reviewer_required
def queue_apps(request):
    use_es = waffle.switch_is_active('reviewer-tools-elasticsearch')
    sort_field = 'nomination'

    queues_helper = ReviewersQueuesHelper(request, use_es=use_es)
    apps = queues_helper.get_pending_queue()
    apps = queues_helper.sort(apps, date_sort=sort_field)

    if use_es:
        apps = [QueuedApp(app, app.latest_version.nomination_date)
                for app in apps.execute()]
    else:
        apps = [QueuedApp(app, app.all_versions[0].nomination)
                for app in Webapp.version_and_file_transformer(apps)]

    return _queue(request, apps, 'pending', date_sort='nomination',
                  use_es=use_es)


@reviewer_required
def queue_region(request, region=None):
    # TODO: Create a landing page that lists all the special regions.
    if region is None:
        raise http.Http404

    region = parse_region(region)
    column = '_geodata__region_%s_nominated' % region.slug

    queues_helper = ReviewersQueuesHelper(request)
    qs = Webapp.objects.pending_in_region(region)
    apps = [ActionableQueuedApp(app, app.geodata.get_nominated_date(region),
                                reverse('approve-region',
                                        args=[app.id, region.slug]))
            for app in queues_helper.sort(qs, date_sort=column)]

    return _queue(request, apps, 'region', date_sort=column,
                  template='reviewers/queue_region.html',
                  data={'region': region})


@permission_required([('Apps', 'ReviewTarako')])
def additional_review(request, queue):
    """HTML page for an additional review queue."""
    sort_descending = request.GET.get('order') == 'desc'
    # TODO: Add `.select_related('app')`. Currently it won't load the name.
    additional_reviews = AdditionalReview.objects.unreviewed(
        queue=queue, and_approved=True, descending=sort_descending)
    apps = [ActionableQueuedApp(additional_review.app,
                                additional_review.created,
                                reverse('additionalreview-detail',
                                        args=[additional_review.pk]))
            for additional_review in additional_reviews]
    return _queue(request, apps, queue, date_sort='created',
                  template='reviewers/additional_review.html',
                  data={'queue': queue})


@reviewer_required
def queue_rereview(request):
    use_es = waffle.switch_is_active('reviewer-tools-elasticsearch')

    queues_helper = ReviewersQueuesHelper(request, use_es=use_es)
    apps = queues_helper.get_rereview_queue()
    apps = queues_helper.sort(apps, date_sort='created')

    if use_es:
        apps = [QueuedApp(app, app.rereview_date) for app in apps.execute()]
    else:
        apps = [QueuedApp(app, app.rereviewqueue_set.all()[0].created)
                for app in apps]

    return _queue(request, apps, 'rereview', date_sort='created',
                  use_es=use_es)


@permission_required([('Apps', 'ReviewEscalated')])
def queue_escalated(request):
    use_es = waffle.switch_is_active('reviewer-tools-elasticsearch')

    queues_helper = ReviewersQueuesHelper(request, use_es=use_es)
    apps = queues_helper.get_escalated_queue()
    apps = queues_helper.sort(apps, date_sort='created')

    if use_es:
        apps = [QueuedApp(app, app.escalation_date) for app in apps.execute()]
    else:
        apps = [QueuedApp(app, app.escalationqueue_set.all()[0].created)
                for app in apps]

    return _queue(request, apps, 'escalated', date_sort='created',
                  use_es=use_es)


@reviewer_required
def queue_updates(request):
    use_es = waffle.switch_is_active('reviewer-tools-elasticsearch')

    queues_helper = ReviewersQueuesHelper(request, use_es=use_es)
    apps = queues_helper.get_updates_queue()
    apps = queues_helper.sort(apps, date_sort='nomination')

    if use_es:
        apps = [QueuedApp(app, app.latest_version.nomination_date)
                for app in apps.execute()]
    else:
        apps = [QueuedApp(app, app.all_versions[0].nomination)
                for app in Webapp.version_and_file_transformer(apps)]

    return _queue(request, apps, 'updates', date_sort='nomination',
                  use_es=use_es)


@permission_required([('Apps', 'ModerateReview')])
def queue_moderated(request):
    """Queue for reviewing app reviews."""
    queues_helper = ReviewersQueuesHelper(request)
    qs = queues_helper.get_moderated_queue()

    page = paginate(request, qs, per_page=20)
    flags = dict(ReviewFlag.FLAGS)
    reviews_formset = ReviewFlagFormSet(request.POST or None,
                                        queryset=page.object_list,
                                        request=request)

    if reviews_formset.is_valid():
        reviews_formset.save()
        return redirect(reverse('reviewers.apps.queue_moderated'))

    return render(request, 'reviewers/queue.html',
                  context(request, reviews_formset=reviews_formset,
                          tab='moderated', page=page, flags=flags))


@permission_required([('Apps', 'ReadAbuse')])
def queue_abuse(request):
    """Queue for reviewing abuse reports."""
    queues_helper = ReviewersQueuesHelper(request)
    apps = queues_helper.get_abuse_queue()

    page = paginate(request, apps, per_page=20)
    abuse_formset = AbuseViewFormSet(request.POST or None,
                                     queryset=page.object_list,
                                     request=request)

    if abuse_formset.is_valid():
        abuse_formset.save()
        return redirect(reverse('reviewers.apps.queue_abuse'))

    return render(request, 'reviewers/queue.html',
                  context(request, abuse_formset=abuse_formset,
                          tab='abuse', page=page))


def _get_search_form(request):
    form = ApiReviewersSearchForm()
    fields = [f.name for f in form.visible_fields() + form.hidden_fields()]
    get = dict((k, v) for k, v in request.GET.items() if k in fields)
    return ApiReviewersSearchForm(get or None)


@reviewer_required
def logs(request):
    data = request.GET.copy()

    if not data.get('start') and not data.get('end'):
        today = datetime.date.today()
        data['start'] = today - datetime.timedelta(days=30)

    form = forms.ReviewLogForm(data)

    approvals = ActivityLog.objects.review_queue(webapp=True)

    if form.is_valid():
        data = form.cleaned_data
        if data.get('start'):
            approvals = approvals.filter(created__gte=data['start'])
        if data.get('end'):
            approvals = approvals.filter(created__lt=data['end'])
        if data.get('search'):
            term = data['search']
            approvals = approvals.filter(
                Q(commentlog__comments__icontains=term) |
                Q(applog__addon__name__localized_string__icontains=term) |
                Q(applog__addon__app_slug__icontains=term) |
                Q(user__display_name__icontains=term) |
                Q(user__email__icontains=term)).distinct()

    pager = paginate(request, approvals, 50)
    data = context(request, form=form, pager=pager, ACTION_DICT=mkt.LOG_BY_ID,
                   tab='logs')
    return render(request, 'reviewers/logs.html', data)


@reviewer_required
def motd(request):
    form = None
    motd = unmemoized_get_config('mkt_reviewers_motd')
    if acl.action_allowed(request, 'AppReviewerMOTD', 'Edit'):
        form = MOTDForm(request.POST or None, initial={'motd': motd})
    if form and request.method == 'POST' and form.is_valid():
        set_config(u'mkt_reviewers_motd', form.cleaned_data['motd'])
        messages.success(request, _('Changes successfully saved.'))
        return redirect(reverse('reviewers.apps.motd'))
    data = context(request, form=form)
    return render(request, 'reviewers/motd.html', data)


def _get_permissions(manifest):
    permissions = {}

    for perm in manifest.get('permissions', {}).keys():
        pval = permissions[perm] = {'type': 'web'}
        if perm in PERMISSIONS['privileged']:
            pval['type'] = 'priv'
        elif perm in PERMISSIONS['certified']:
            pval['type'] = 'cert'

        pval['description'] = manifest['permissions'][perm].get('description')

    return permissions


def _get_manifest_json(addon):
    return addon.get_manifest_json(addon.versions.latest().all_files[0])


@permission_required([('AppLookup', 'View'), ('Apps', 'Review')])
@app_view_with_deleted
@json_view
def app_view_manifest(request, addon):
    headers = {}
    manifest = {}
    success = False

    if addon.is_packaged:
        manifest = _get_manifest_json(addon)
        content = json.dumps(manifest, indent=4)
        success = True

    else:  # Show the hosted manifest_url.
        content, headers = u'', {}
        if addon.manifest_url:
            try:
                req = requests.get(
                    addon.manifest_url, verify=False,
                    headers={'User-Agent': settings.MARKETPLACE_USER_AGENT})
                content, headers = req.content, req.headers
                success = True
            except Exception:
                content = u''.join(traceback.format_exception(*sys.exc_info()))
            else:
                success = True

            try:
                # Reindent the JSON.
                manifest = json.loads(content)
                content = json.dumps(manifest, indent=4)
            except:
                # If it's not valid JSON, just return the content as is.
                pass

    return {
        'content': jinja2.escape(smart_decode(content)),
        'headers': dict((jinja2.escape(k), jinja2.escape(v))
                        for k, v in headers.items()),
        'success': success,
        # Note: We're using `escape_all` on the values here since we know the
        # keys of the nested dict don't come from user input (manifest) and are
        # known safe.
        'permissions': dict((jinja2.escape(k), escape_all(v))
                            for k, v in _get_permissions(manifest).items())
    }


def reviewer_or_token_required(f):
    @functools.wraps(f)
    def wrapper(request, addon, *args, **kw):
        # If there is a 'token' in request.GET we either return 200 or 403.
        # Otherwise we treat it like a normal django view and redirect to a
        # login page or check for Apps:Review permissions.
        allowed = False
        token = request.GET.get('token')

        if token and Token.pop(token, data={'app_id': addon.id}):
            log.info('Token for app:%s was successfully used' % addon.id)
            allowed = True
        elif not token and not request.user.is_authenticated():
            return redirect_for_login(request)
        elif acl.action_allowed(request, 'Apps', 'Review'):
            allowed = True

        if allowed:
            if token:
                log.info('Token provided for app:%s and all was happy'
                         % addon.id)
            else:
                log.info('Apps:Review (no token) all happy for app:%s'
                         % addon.id)
            return f(request, addon, *args, **kw)
        else:
            if token:
                log.info('Token provided for app:%s but was not valid'
                         % addon.id)
            else:
                log.info('Apps:Review permissions not met for app:%s'
                         % addon.id)
            raise PermissionDenied

    return wrapper


@app_view
@reviewer_or_token_required
def mini_manifest(request, addon, version_id):
    token = request.GET.get('token')
    return http.HttpResponse(_mini_manifest(addon, version_id, token),
                             content_type=MANIFEST_CONTENT_TYPE)


def _mini_manifest(addon, version_id, token=None):
    if not addon.is_packaged:
        raise http.Http404

    version = get_object_or_404(addon.versions, pk=version_id)
    file_ = version.all_files[0]
    manifest = addon.get_manifest_json(file_)

    package_path = absolutify(
        reverse('reviewers.signed', args=[addon.app_slug, version.id]))

    if token:
        # Generate a fresh token.
        token = Token(data={'app_id': addon.id})
        token.save()
        package_path = urlparams(package_path, token=token.token)

    data = {
        'name': manifest['name'],
        'version': version.version,
        'size': file_.size,
        'release_notes': version.releasenotes,
        'package_path': package_path,
    }
    for key in ['developer', 'icons', 'locales']:
        if key in manifest:
            data[key] = manifest[key]

    return json.dumps(data, cls=JSONEncoder)


@reviewer_required
@app_view
def app_abuse(request, addon):
    reports = AbuseReport.objects.filter(addon=addon).order_by('-created')
    total = reports.count()
    reports = paginate(request, reports, count=total)
    return render(request, 'reviewers/abuse.html',
                  context(request, addon=addon, reports=reports,
                          total=total))


@app_view
@reviewer_or_token_required
def get_signed_packaged(request, addon, version_id):
    version = get_object_or_404(addon.versions, pk=version_id)
    file = version.all_files[0]
    path = addon.sign_if_packaged(version.pk, reviewer=True)
    if not path:
        raise http.Http404
    log.info('Returning signed package addon: %s, version: %s, path: %s' %
             (addon.pk, version_id, path))
    return HttpResponseSendFile(request, path, content_type='application/zip',
                                etag=file.hash.split(':')[-1])


@reviewer_required(moderator=True)
def performance(request, email=None):
    is_admin = acl.action_allowed(request, 'Admin', '%')

    if email:
        if email == request.user.email:
            user = request.user
        elif is_admin:
            user = get_object_or_404(UserProfile, email=email)
        else:
            raise http.Http404
    else:
        user = request.user

    today = datetime.date.today()
    month_ago = today - datetime.timedelta(days=30)
    year_ago = today - datetime.timedelta(days=365)

    total = ReviewerScore.get_total(user)
    totals = ReviewerScore.get_performance(user)
    months = ReviewerScore.get_performance_since(user, month_ago)
    years = ReviewerScore.get_performance_since(user, year_ago)

    def _sum(iter):
        return sum(s.total or 0 for s in iter)

    performance = {
        'month': _sum(months),
        'year': _sum(years),
        'total': _sum(totals),
    }

    ctx = context(request, **{
        'profile': user,
        'total': total,
        'performance': performance,
    })

    return render(request, 'reviewers/performance.html', ctx)


@reviewer_required(moderator=True)
def leaderboard(request):
    return render(request, 'reviewers/leaderboard.html',
                  context(request,
                          **{'scores': ReviewerScore.all_users_by_score()}))


@reviewer_required
@json_view
def apps_reviewing(request):
    return render(request, 'reviewers/apps_reviewing.html',
                  context(request,
                          **{'tab': 'reviewing',
                             'apps': AppsReviewing(request).get_apps()}))


@reviewer_required
def attachment(request, attachment):
    """
    Serve an attachment directly to the user.
    """
    try:
        a = ActivityLogAttachment.objects.get(pk=attachment)
        full_path = os.path.join(settings.REVIEWER_ATTACHMENTS_PATH,
                                 a.filepath)
        fsock = open(full_path, 'r')
    except (ActivityLogAttachment.DoesNotExist, IOError,):
        response = http.HttpResponseNotFound()
    else:
        filename = urllib.quote(a.filename())
        response = http.HttpResponse(fsock,
                                     content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename=%s' % filename
        response['Content-Length'] = os.path.getsize(full_path)
    return response


def _retrieve_translation(text, language):
    try:
        r = requests.get(
            settings.GOOGLE_TRANSLATE_API_URL, params={
                'key': getattr(settings, 'GOOGLE_API_CREDENTIALS', ''),
                'q': text, 'target': language},
            headers={'User-Agent': settings.MARKETPLACE_USER_AGENT})
    except Exception, e:
        log.error(e)
        raise
    try:
        translated = (HTMLParser.HTMLParser().unescape(
            r.json()['data']['translations'][0]['translatedText']))
    except (KeyError, IndexError):
        translated = ''
    return translated, r


@waffle_switch('reviews-translate')
@permission_required([('Apps', 'ModerateReview')])
def review_translate(request, app_slug, review_pk, language):
    review = get_object_or_404(Review, addon__app_slug=app_slug, pk=review_pk)

    if '-' in language:
        language = language.split('-')[0]

    if request.is_ajax():
        title = ''
        body = ''
        status = 200

        if review.title is not None:
            title, r = _retrieve_translation(review.title, language)
            if r.status_code != 200:
                status = r.status_code

        if review.body is not None:
            body, r = _retrieve_translation(review.body, language)
            if r.status_code != 200:
                status = r.status_code

        return http.HttpResponse(json.dumps({'title': title, 'body': body}),
                                 status=status)
    else:
        return redirect(settings.GOOGLE_TRANSLATE_REDIRECT_URL.format(
            lang=language, text=review.body))


@waffle_switch('reviews-translate')
@permission_required([('Apps', 'ReadAbuse')])
def abuse_report_translate(request, app_slug, report_pk, language):
    report = get_object_or_404(AbuseReport, addon__app_slug=app_slug,
                               pk=report_pk)

    if '-' in language:
        language = language.split('-')[0]

    if request.is_ajax():
        if report.message is not None:
            trans, r = _retrieve_translation(report.message, language)

            return http.HttpResponse(json.dumps({'body': trans}),
                                     status=r.status_code)
    else:
        return redirect(settings.GOOGLE_TRANSLATE_REDIRECT_URL.format(
            lang=language, text=report.message))


class ReviewingView(ListAPIView):
    authentication_classes = [RestOAuthAuthentication,
                              RestSharedSecretAuthentication]
    permission_classes = [GroupPermission('Apps', 'Review')]
    serializer_class = ReviewingSerializer

    def get_queryset(self):
        return [row['app'] for row in AppsReviewing(self.request).get_apps()]


class ReviewersSearchView(SearchView):
    permission_classes = [GroupPermission('Apps', 'Review')]
    filter_backends = [SearchQueryFilter, ReviewerSearchFormFilter,
                       SortingFilter]
    form_class = ApiReviewersSearchForm
    serializer_class = ReviewersESAppSerializer


class ApproveRegion(SlugOrIdMixin, CreateAPIView):
    """
    TODO: Document this API.
    """
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    model = Webapp
    slug_field = 'app_slug'

    def get_permissions(self):
        region = parse_region(self.request.parser_context['kwargs']['region'])
        region_slug = region.slug.upper()
        return (GroupPermission('Apps', 'ReviewRegion%s' % region_slug),)

    def get_queryset(self):
        region = parse_region(self.request.parser_context['kwargs']['region'])
        return self.model.objects.pending_in_region(region)

    def post(self, request, pk, region, *args, **kwargs):
        app = self.get_object()
        region = parse_region(region)

        form = ApproveRegionForm(request.DATA, app=app, region=region)
        if not form.is_valid():
            raise ParseError(dict(form.errors.items()))
        form.save()

        return Response({'approved': bool(form.cleaned_data['approve'])})


class _AppAction(SlugOrIdMixin):
    permission_classes = [GroupPermission('Apps', 'Review')]
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    model = Webapp
    slug_field = 'app_slug'

    def _do_post(self, request, pk):
        app = self.get_object()
        handler = ReviewApp(request, app, app.latest_version, ())
        handler.set_data(request.DATA)
        return getattr(handler, "process_" + self.verb)()

    def post(self, request, pk, *a, **kw):
        self._do_post(request, pk)
        return Response()


class AppApprove(_AppAction, CreateAPIView):
    verb = "approve"

    def post(self, request, pk, *a, **kw):
        result = self._do_post(request, pk)
        if result is None:
            return Response(status=409)
        return Response({'score': result})


class AppReject(_AppAction, CreateAPIView):
    verb = "reject"

    def post(self, request, pk, *a, **kw):
        result = self._do_post(request, pk)
        return Response({'score': result})


class AppInfo(_AppAction, CreateAPIView):
    verb = "request_information"


class AppEscalate(_AppAction, CreateAPIView, DestroyAPIView):
    permission_classes = [ByHttpMethod({
        'options': AllowAny,
        'post': GroupPermission('Apps', 'Review'),
        'delete': GroupPermission('Apps', 'Edit'),
    })]
    verb = "escalate"

    def delete(self, request, pk, *a, **kw):
        app = self.get_object()
        handler = ReviewApp(request, app, app.latest_version, ())
        handler.set_data(request.QUERY_PARAMS)
        handler.process_clear_escalation()
        return Response()


class AppDisable(_AppAction, CreateAPIView):
    permission_classes = [GroupPermission('Apps', 'Edit')]
    verb = "disable"


class AppRereview(_AppAction, DestroyAPIView):

    def delete(self, request, pk, *a, **kw):
        app = self.get_object()
        handler = ReviewApp(request, app, app.latest_version, ())
        handler.set_data(request.QUERY_PARAMS)
        result = handler.process_clear_rereview()
        return Response({'score': result})


class AppReviewerComment(_AppAction, CreateAPIView):
    verb = "comment"


class _WebsiteAction(object):
    permission_classes = [GroupPermission('Websites', 'Review')]
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    model = Website


class WebsiteApprove(_WebsiteAction, CreateAPIView):
    def post(self, request, pk, *a, **kw):
        website = self.get_object()
        website.update(status=mkt.STATUS_PUBLIC)
        return Response()


class WebsiteReject(_WebsiteAction, CreateAPIView):
    def post(self, request, pk, *a, **kw):
        website = self.get_object()
        website.update(status=mkt.STATUS_REJECTED)
        return Response()


class UpdateAdditionalReviewViewSet(SlugOrIdMixin, UpdateAPIView):
    """
    API ViewSet for setting pass/fail of an AdditionalReview. This does not
    follow the DRF convention but instead calls review_passed() or
    review_failed() on the AdditionalReview based on request.DATA['passed'].
    """

    model = AdditionalReview
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    serializer_class = ReviewerAdditionalReviewSerializer
    # TODO: Change this when there is more than just the Tarako queue.
    permission_classes = [GroupPermission('Apps', 'ReviewTarako')]

    def pre_save(self, additional_review):
        additional_review.reviewer = self.request.user
        additional_review.review_completed = datetime.datetime.now()

    def post_save(self, additional_review, created):
        additional_review.execute_post_review_task()


class AppOwnerPermission(BasePermission):
    def webapp_exists(self, app_id):
        return Webapp.objects.filter(pk=app_id).exists()

    def user_is_author(self, app_id, user):
        return AddonUser.objects.filter(user=user, addon_id=app_id).exists()

    def has_permission(self, request, view):
        app_id = request.DATA.get('app')
        if not app_id or not self.webapp_exists(app_id):
            # Fall through to a 400 for invalid data.
            return True
        else:
            return self.user_is_author(app_id, request.user)


class CreateAdditionalReviewViewSet(CreateAPIView):
    """
    API ViewSet for requesting an additional review.
    """

    model = AdditionalReview
    serializer_class = AdditionalReviewSerializer
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    # TODO: Change this when there is more than just the Tarako queue.
    permission_classes = [AnyOf(AppOwnerPermission,
                                GroupPermission('Apps', 'Edit'))]

    def app(self, app_id):
        self.app = Webapp.objects.get(pk=app_id)
        return self.app


class GenerateToken(SlugOrIdMixin, CreateAPIView):
    """
    This generates a short-lived token to be used by the APK factory service
    for authentication of requests to the reviewer mini-manifest and package.

    """
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = [GroupPermission('Apps', 'Review')]
    model = Webapp
    slug_field = 'app_slug'

    def post(self, request, pk, *args, **kwargs):
        app = self.get_object()
        token = Token(data={'app_id': app.id})
        token.save()

        log.info('Generated token on app:%s for user:%s' % (
            app.id, request.user.id))

        return Response({'token': token.token})


@never_cache
@json_view
@reviewer_required
def review_viewing(request):
    if 'addon_id' not in request.POST:
        return {}

    addon_id = request.POST['addon_id']
    user_id = request.user.id
    current_name = ''
    is_user = 0
    key = '%s:review_viewing:%s' % (settings.CACHE_PREFIX, addon_id)
    interval = mkt.EDITOR_VIEWING_INTERVAL

    # Check who is viewing.
    currently_viewing = cache.get(key)

    # If nobody is viewing or current user is, set current user as viewing
    if not currently_viewing or currently_viewing == user_id:
        # We want to save it for twice as long as the ping interval,
        # just to account for latency and the like.
        cache.set(key, user_id, interval * 2)
        currently_viewing = user_id
        current_name = request.user.name
        is_user = 1
    else:
        current_name = UserProfile.objects.get(pk=currently_viewing).name

    AppsReviewing(request).add(addon_id)

    return {'current': currently_viewing, 'current_name': current_name,
            'is_user': is_user, 'interval_seconds': interval}


@never_cache
@json_view
@reviewer_required
def queue_viewing(request):
    if 'addon_ids' not in request.POST:
        return {}

    viewing = {}
    user_id = request.user.id

    for addon_id in request.POST['addon_ids'].split(','):
        addon_id = addon_id.strip()
        key = '%s:review_viewing:%s' % (settings.CACHE_PREFIX, addon_id)
        currently_viewing = cache.get(key)
        if currently_viewing and currently_viewing != user_id:
            viewing[addon_id] = (UserProfile.objects
                                            .get(id=currently_viewing)
                                            .display_name)

    return viewing


class CannedResponseViewSet(CORSMixin, MarketplaceView, viewsets.ModelViewSet):
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = [GroupPermission('Admin', 'ReviewerTools')]
    model = CannedResponse
    serializer_class = CannedResponseSerializer
    cors_allowed_methods = ['get', 'post', 'patch', 'put', 'delete']


class ReviewerScoreViewSet(CORSMixin, MarketplaceView, viewsets.ModelViewSet):
    authentication_classes = (RestOAuthAuthentication,
                              RestSharedSecretAuthentication)
    permission_classes = [GroupPermission('Admin', 'ReviewerTools')]
    serializer_class = ReviewerScoreSerializer
    cors_allowed_methods = ['get', 'post', 'patch', 'put', 'delete']

    # mkt.REVIEWED_MANUAL is the default so we don't need to set it on the
    # instance when we are creating a new one, but we do need to set it on
    # queryset to prevent instances with other note_key values from ever being
    # returned.
    queryset = ReviewerScore.objects.filter(note_key=mkt.REVIEWED_MANUAL)


@permission_required([('Apps', 'ModerateReview')])
def moderatelog(request):
    form = ModerateLogForm(request.GET)
    modlog = ActivityLog.objects.editor_events()
    if form.is_valid():
        if form.cleaned_data['start']:
            modlog = modlog.filter(created__gte=form.cleaned_data['start'])
        if form.cleaned_data['end']:
            modlog = modlog.filter(created__lt=form.cleaned_data['end'])
        if form.cleaned_data['search']:
            modlog = modlog.filter(action=form.cleaned_data['search'].id)

    pager = paginate(request, modlog, 50)
    data = context(request, form=form, pager=pager, tab='moderatelog')
    return render(request, 'reviewers/moderatelog.html', data)


@permission_required([('Apps', 'ModerateReview')])
def moderatelog_detail(request, eventlog_id):
    log = get_object_or_404(
        ActivityLog.objects.editor_events(), pk=eventlog_id)
    review = None
    if len(log.arguments) > 1 and isinstance(log.arguments[1], Review):
        review = log.arguments[1]

    form = ModerateLogDetailForm(request.POST or None)
    is_admin = acl.action_allowed(request, 'ReviewerAdminTools', 'View')
    can_undelete = review and review.deleted and (
        is_admin or request.user.pk == log.user.pk)

    if (request.method == 'POST' and form.is_valid() and
            form.cleaned_data['action'] == 'undelete'):
        if not can_undelete:
            if not review:
                raise RuntimeError('Review doesn`t exist.')
            elif not review.deleted:
                raise RuntimeError('Review isn`t deleted.')
            else:
                raise PermissionDenied
        ReviewerScore.award_moderation_points(
            log.user, review.addon, review.id, undo=True)
        review.undelete()
        return redirect('reviewers.apps.moderatelog.detail', eventlog_id)
    data = context(request, log=log, form=form, review=review,
                   can_undelete=can_undelete)
    return render(request, 'reviewers/moderatelog_detail.html', data)
