import csv
from urlparse import urlparse

from django import http
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage as storage
from django.db.models.loading import cache as app_cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views import debug
from django.views.decorators.cache import never_cache

import commonware.log
import jinja2
from hera.contrib.django_forms import FlushForm
from hera.contrib.django_utils import flush_urls, get_hera

import amo
from addons.decorators import addon_view
from addons.models import AddonUser
from amo import messages
from amo.decorators import any_permission_required, json_view, post_required
from amo.mail import FakeEmailBackend
from amo.urlresolvers import reverse
from amo.utils import chunked
from devhub.models import ActivityLog
from files.models import File
from market.utils import update_from_csv
from users.models import UserProfile
from zadmin.forms import GenerateErrorForm, PriceTiersForm

from . import tasks
from .decorators import admin_required
from .forms import AddonStatusForm, DevMailerForm, FileFormSet, YesImSure
from .models import EmailPreviewTopic


log = commonware.log.getLogger('z.zadmin')


@admin.site.admin_view
def hera(request):
    form = FlushForm(initial={'flushprefix': settings.SITE_URL})

    boxes = []
    configured = False  # Default to not showing the form.
    for i in settings.HERA:
        hera = get_hera(i)
        r = {'location': urlparse(i['LOCATION'])[1], 'stats': False}
        if hera:
            r['stats'] = hera.getGlobalCacheInfo()
            configured = True
        boxes.append(r)

    if not configured:
        messages.error(request, "Hera is not (or mis-)configured.")
        form = None

    if request.method == 'POST' and hera:
        form = FlushForm(request.POST)
        if form.is_valid():
            expressions = request.POST['flushlist'].splitlines()

            for url in expressions:
                num = flush_urls([url], request.POST['flushprefix'], True)
                msg = ("Flushed %d objects from front end cache for: %s"
                       % (len(num), url))
                log.info("[Hera] (user:%s) %s" % (request.user, msg))
                messages.success(request, msg)

    return render(request, 'zadmin/hera.html', {'form': form, 'boxes': boxes})


@admin_required
def show_settings(request):
    settings_dict = debug.get_safe_settings()

    # sigh
    settings_dict['HERA'] = []
    for i in settings.HERA:
        settings_dict['HERA'].append(debug.cleanse_setting('HERA', i))

    # Retain this so that legacy PAYPAL_CGI_AUTH variables in settings_local
    # are not exposed.
    for i in ['PAYPAL_EMBEDDED_AUTH', 'PAYPAL_CGI_AUTH',
              'GOOGLE_ANALYTICS_CREDENTIALS']:
        settings_dict[i] = debug.cleanse_setting(i,
                                                 getattr(settings, i, {}))

    settings_dict['WEBAPPS_RECEIPT_KEY'] = '********************'

    return render(request, 'zadmin/settings.html',
                  {'settings_dict': settings_dict})


@admin_required
def env(request):
    return http.HttpResponse(u'<pre>%s</pre>' % (jinja2.escape(request)))


@admin.site.admin_view
def fix_disabled_file(request):
    file_ = None
    if request.method == 'POST' and 'file' in request.POST:
        file_ = get_object_or_404(File, id=request.POST['file'])
        if 'confirm' in request.POST:
            file_.unhide_disabled_file()
            messages.success(request, 'We have done a great thing.')
            return redirect('zadmin.fix-disabled')
    return render(request, 'zadmin/fix-disabled.html',
                  {'file': file_, 'file_id': request.POST.get('file', '')})


@any_permission_required([('Admin', '%'),
                          ('BulkValidationAdminTools', 'View')])
def email_preview_csv(request, topic):
    resp = http.HttpResponse()
    resp['Content-Type'] = 'text/csv; charset=utf-8'
    resp['Content-Disposition'] = "attachment; filename=%s.csv" % (topic)
    writer = csv.writer(resp)
    fields = ['from_email', 'recipient_list', 'subject', 'body']
    writer.writerow(fields)
    rs = EmailPreviewTopic(topic=topic).filter().values_list(*fields)
    for row in rs:
        writer.writerow([r.encode('utf8') for r in row])
    return resp


@admin.site.admin_view
def mail(request):
    backend = FakeEmailBackend()
    if request.method == 'POST':
        backend.clear()
        return redirect('zadmin.mail')
    return render(request, 'zadmin/mail.html', dict(mail=backend.view_all()))


@admin.site.admin_view
def email_devs(request):
    form = DevMailerForm(request.POST or None)
    preview = EmailPreviewTopic(topic='email-devs')
    if preview.filter().count():
        preview_csv = reverse('zadmin.email_preview_csv',
                              args=[preview.topic])
    else:
        preview_csv = None
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        qs = (AddonUser.objects.filter(role__in=(amo.AUTHOR_ROLE_DEV,
                                                 amo.AUTHOR_ROLE_OWNER))
                               .exclude(user__email=None))

        if data['recipients'] in ('payments', 'desktop_apps'):
            qs = qs.exclude(addon__status=amo.STATUS_DELETED)
        else:
            qs = qs.filter(addon__status__in=amo.LISTED_STATUSES)

        if data['recipients'] == 'eula':
            qs = qs.exclude(addon__eula=None)
        elif data['recipients'] in ('payments',
                                    'payments_region_enabled',
                                    'payments_region_disabled'):
            qs = qs.filter(addon__type=amo.ADDON_WEBAPP)
            qs = qs.exclude(addon__premium_type__in=(amo.ADDON_FREE,
                                                     amo.ADDON_OTHER_INAPP))
            if data['recipients'] == 'payments_region_enabled':
                qs = qs.filter(addon__enable_new_regions=True)
            elif data['recipients'] == 'payments_region_disabled':
                qs = qs.filter(addon__enable_new_regions=False)
        elif data['recipients'] in ('apps', 'free_apps_region_enabled',
                                    'free_apps_region_disabled'):
            qs = qs.filter(addon__type=amo.ADDON_WEBAPP)
            if data['recipients'] == 'free_apps_region_enabled':
                qs = qs.filter(addon__enable_new_regions=True)
            elif data['recipients'] == 'free_apps_region_disabled':
                qs = qs.filter(addon__enable_new_regions=False)
        elif data['recipients'] == 'desktop_apps':
            qs = (qs.filter(addon__type=amo.ADDON_WEBAPP,
                addon__addondevicetype__device_type=amo.DEVICE_DESKTOP.id))
        elif data['recipients'] == 'sdk':
            qs = qs.exclude(addon__versions__files__jetpack_version=None)
        elif data['recipients'] == 'all_extensions':
            qs = qs.filter(addon__type=amo.ADDON_EXTENSION)
        else:
            raise NotImplementedError('If you want to support emailing other '
                                      'types of developers, do it here!')
        if data['preview_only']:
            # Clear out the last batch of previewed emails.
            preview.filter().delete()
        total = 0
        for emails in chunked(set(qs.values_list('user__email', flat=True)),
                              100):
            total += len(emails)
            tasks.admin_email.delay(emails, data['subject'], data['message'],
                                    preview_only=data['preview_only'],
                                    preview_topic=preview.topic)
        msg = 'Emails queued for delivery: %s' % total
        if data['preview_only']:
            msg = '%s (for preview only, emails not sent!)' % msg
        messages.success(request, msg)
        return redirect('zadmin.email_devs')
    return render(request, 'zadmin/email-devs.html',
                  dict(form=form, preview_csv=preview_csv))


@any_permission_required([('Admin', '%'),
                          ('AdminTools', 'View'),
                          ('ReviewerAdminTools', 'View'),
                          ('BulkValidationAdminTools', 'View')])
def index(request):
    log = ActivityLog.objects.admin_events()[:5]
    return render(request, 'zadmin/index.html', {'log': log})


@never_cache
@json_view
def general_search(request, app_id, model_id):
    if not admin.site.has_permission(request):
        raise PermissionDenied

    model = app_cache.get_model(app_id, model_id)
    if not model:
        raise http.Http404

    limit = 10
    obj = admin.site._registry[model]
    ChangeList = obj.get_changelist(request)
    # This is a hideous api, but uses the builtin admin search_fields API.
    # Expecting this to get replaced by ES so soon, that I'm not going to lose
    # too much sleep about it.
    cl = ChangeList(request, obj.model, [], [], [], [], obj.search_fields, [],
                    obj.list_max_show_all, limit, [], obj)
    qs = cl.get_query_set(request)
    # Override search_fields_response on the ModelAdmin object
    # if you'd like to pass something else back to the front end.
    lookup = getattr(obj, 'search_fields_response', None)
    return [{'value': o.pk, 'label': getattr(o, lookup) if lookup else str(o)}
            for o in qs[:limit]]


@admin_required(reviewers=True)
@addon_view
def addon_manage(request, addon):

    form = AddonStatusForm(request.POST or None, instance=addon)
    pager = amo.utils.paginate(request, addon.versions.all(), 30)
    # A list coercion so this doesn't result in a subquery with a LIMIT which
    # MySQL doesn't support (at this time).
    versions = list(pager.object_list)
    files = File.objects.filter(version__in=versions).select_related('version')
    formset = FileFormSet(request.POST or None, queryset=files)

    if form.is_valid() and formset.is_valid():
        if 'status' in form.changed_data:
            amo.log(amo.LOG.CHANGE_STATUS, addon, form.cleaned_data['status'])
            log.info('Addon "%s" status changed to: %s' % (
                addon.slug, form.cleaned_data['status']))
            form.save()
        if 'highest_status' in form.changed_data:
            log.info('Addon "%s" highest status changed to: %s' % (
                addon.slug, form.cleaned_data['highest_status']))
            form.save()

        if 'outstanding' in form.changed_data:
            log.info('Addon "%s" changed to%s outstanding' % (addon.slug,
                     '' if form.cleaned_data['outstanding'] else ' not'))
            form.save()

        for form in formset:
            if 'status' in form.changed_data:
                log.info('Addon "%s" file (ID:%d) status changed to: %s' % (
                    addon.slug, form.instance.id, form.cleaned_data['status']))
                form.save()
        return redirect('zadmin.addon_manage', addon.slug)

    # Build a map from file.id to form in formset for precise form display
    form_map = dict((form.instance.id, form) for form in formset.forms)
    # A version to file map to avoid an extra query in the template
    file_map = {}
    for file in files:
        file_map.setdefault(file.version_id, []).append(file)

    return render(request, 'zadmin/addon_manage.html', {
        'addon': addon, 'pager': pager, 'versions': versions, 'form': form,
        'formset': formset, 'form_map': form_map, 'file_map': file_map})


@admin.site.admin_view
@post_required
@json_view
def recalc_hash(request, file_id):

    file = get_object_or_404(File, pk=file_id)
    file.size = storage.size(file.file_path)
    file.hash = file.generate_hash()
    file.save()

    log.info('Recalculated hash for file ID %d' % file.id)
    messages.success(request,
                     'File hash and size recalculated for file %d.' % file.id)
    return {'success': 1}


@admin.site.admin_view
def memcache(request):
    form = YesImSure(request.POST or None)
    if form.is_valid() and form.cleaned_data['yes']:
        cache.clear()
        form = YesImSure()
        messages.success(request, 'Cache cleared')
    if cache._cache and hasattr(cache._cache, 'get_stats'):
        stats = cache._cache.get_stats()
    else:
        stats = []
    return render(request, 'zadmin/memcache.html',
                  {'form': form, 'stats': stats})


@admin_required
def generate_error(request):
    form = GenerateErrorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.explode()
    return render(request, 'zadmin/generate-error.html', {'form': form})


@any_permission_required([('Admin', '%'),
                          ('MailingLists', 'View')])
def export_email_addresses(request):
    return render(request, 'zadmin/export_button.html', {})


@any_permission_required([('Admin', '%'),
                          ('MailingLists', 'View')])
def email_addresses_file(request):
    resp = http.HttpResponse()
    resp['Content-Type'] = 'text/plain; charset=utf-8'
    resp['Content-Disposition'] = ('attachment; '
                                   'filename=amo_optin_emails.txt')
    emails = (UserProfile.objects.filter(notifications__notification_id=13,
                                         notifications__enabled=1)
              .values_list('email', flat=True))
    for e in emails:
        if e is not None:
            resp.write(e + '\n')
    return resp


@admin_required
def price_tiers(request):
    output = []
    form = PriceTiersForm(request.POST or None, request.FILES)
    if request.method == 'POST' and form.is_valid():
        output = update_from_csv(form.cleaned_data['prices'])

    return render(request, 'zadmin/update-prices.html',
                  {'result': output, 'form': form})
