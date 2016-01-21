import csv

from django import http
from django.conf import settings
from django.contrib import admin, messages
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views import debug

import commonware.log
import elasticsearch
import jinja2

import mkt
from mkt.developers.models import ActivityLog
from mkt.prices.utils import update_from_csv
from mkt.site.decorators import permission_required
from mkt.site.mail import FakeEmailBackend
from mkt.site.utils import chunked
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonUser, Webapp
from mkt.webapps.tasks import update_manifests

from . import tasks
from .decorators import admin_required
from .forms import DevMailerForm, GenerateErrorForm, PriceTiersForm, YesImSure
from .models import EmailPreviewTopic


log = commonware.log.getLogger('z.zadmin')


@admin_required
def memory_profile(request):
    import tempfile
    from meliae.scanner import dump_all_objects
    f = tempfile.TemporaryFile()
    dump_all_objects(f)
    f.seek(0)
    return http.HttpResponse(f.read(), content_type='application/json')


@admin_required
def show_settings(request):
    settings_dict = debug.get_safe_settings()

    for i in ['GOOGLE_ANALYTICS_CREDENTIALS']:
        settings_dict[i] = debug.cleanse_setting(i,
                                                 getattr(settings, i, {}))

    settings_dict['WEBAPPS_RECEIPT_KEY'] = '********************'

    return render(request, 'zadmin/settings.html',
                  {'settings_dict': settings_dict})


@admin_required
def env(request):
    return http.HttpResponse(u'<pre>%s</pre>' % (jinja2.escape(request)))


@admin_required
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
        qs = (AddonUser.objects.filter(role__in=(mkt.AUTHOR_ROLE_DEV,
                                                 mkt.AUTHOR_ROLE_OWNER))
                               .exclude(user__email=None))

        if data['recipients'] in ('payments', 'desktop_apps'):
            qs = qs.exclude(addon__status=mkt.STATUS_DELETED)
        else:
            qs = qs.filter(addon__status__in=mkt.LISTED_STATUSES)

        if data['recipients'] in ('payments', 'payments_region_enabled',
                                  'payments_region_disabled'):
            qs = qs.exclude(addon__premium_type__in=(mkt.ADDON_FREE,
                                                     mkt.ADDON_OTHER_INAPP))
            if data['recipients'] == 'payments_region_enabled':
                qs = qs.filter(addon__enable_new_regions=True)
            elif data['recipients'] == 'payments_region_disabled':
                qs = qs.filter(addon__enable_new_regions=False)
        elif data['recipients'] in ('apps', 'free_apps_region_enabled',
                                    'free_apps_region_disabled'):
            if data['recipients'] == 'free_apps_region_enabled':
                qs = qs.filter(addon__enable_new_regions=True)
            elif data['recipients'] == 'free_apps_region_disabled':
                qs = qs.filter(addon__enable_new_regions=False)
        elif data['recipients'] == 'desktop_apps':
            qs = (qs.filter(
                addon__addondevicetype__device_type=mkt.DEVICE_DESKTOP.id))
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


@permission_required([('Admin', '%'),
                      ('AdminTools', 'View'),
                      ('ReviewerAdminTools', 'View')])
def index(request):
    log = ActivityLog.objects.admin_events()[:5]
    return render(request, 'zadmin/index.html', {'log': log})


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


@permission_required([('Admin', '%'),
                      ('MailingLists', 'View')])
def export_email_addresses(request):
    return render(request, 'zadmin/export_button.html', {})


@permission_required([('Admin', '%'),
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


@admin_required(reviewers=True)
def manifest_revalidation(request):
    if request.method == 'POST':
        # Collect the apps to revalidate.
        qs = Q(is_packaged=False, status=mkt.STATUS_PUBLIC,
               disabled_by_user=False)
        webapp_pks = Webapp.objects.filter(qs).values_list('pk', flat=True)

        for pks in chunked(webapp_pks, 100):
            update_manifests.delay(list(pks), check_hash=False)

        messages.success(request, 'Manifest revalidation queued')

    return render(request, 'zadmin/manifest.html')


@admin_required
def elastic(request):
    es = elasticsearch.Elasticsearch(hosts=settings.ES_HOSTS)

    indexes = set(settings.ES_INDEXES.values())
    ctx = {
        'aliases': es.indices.get_aliases(),
        'health': es.cluster.health(),
        'state': es.cluster.state(),
        'mappings': [(index, es.indices.get_mapping(index=index))
                     for index in indexes],
    }
    return render(request, 'zadmin/elastic.html', ctx)
