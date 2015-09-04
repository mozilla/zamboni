import json
import urllib
from collections import OrderedDict
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

import commonware.log
from elasticsearch_dsl import filter as es_filter
from tower import ugettext_lazy as _lazy

import mkt
from mkt.abuse.models import AbuseReport
from mkt.access import acl
from mkt.comm.utils import create_comm_note
from mkt.constants import comm
from mkt.files.models import File
from mkt.ratings.models import Review
from mkt.reviewers.models import EscalationQueue, RereviewQueue, ReviewerScore
from mkt.site.helpers import product_as_dict
from mkt.site.models import manual_order
from mkt.site.utils import cached_property, JSONEncoder
from mkt.translations.query import order_by_translation
from mkt.versions.models import Version
from mkt.webapps.models import Webapp
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.tasks import set_storefront_data
from mkt.websites.models import Website


log = commonware.log.getLogger('z.mailer')


def get_review_type(request, webapp, version):
    if EscalationQueue.objects.filter(webapp=webapp).exists():
        queue = 'escalated'
    elif RereviewQueue.objects.filter(webapp=webapp).exists():
        queue = 'rereview'
    else:
        queue = 'pending'
    return queue


class ReviewBase(object):

    def __init__(self, request, webapp, version, attachment_formset=None,
                 testedon_formset=None):
        self.request = request
        self.user = self.request.user
        self.webapp = webapp
        self.version = version
        self.review_type = get_review_type(request, webapp, version)
        self.files = None
        self.comm_thread = None
        self.attachment_formset = attachment_formset
        self.testedon_formset = testedon_formset
        self.in_pending = self.webapp.status == mkt.STATUS_PENDING
        self.in_rereview = RereviewQueue.objects.filter(
            webapp=self.webapp).exists()
        self.in_escalate = EscalationQueue.objects.filter(
            webapp=self.webapp).exists()

    def get_attachments(self):
        """
        Returns a list of triples suitable to be attached to an email.
        """
        try:
            num = int(self.attachment_formset.data['attachment-TOTAL_FORMS'])
        except (ValueError, TypeError):
            return []
        else:
            files = []
            for i in xrange(num):
                attachment_name = 'attachment-%d-attachment' % i
                attachment = self.request.FILES.get(attachment_name)
                if attachment:
                    attachment.open()
                    files.append((attachment.name, attachment.read(),
                                  attachment.content_type))
            return files

    def set_webapp(self, **kw):
        """Alters webapp using provided kwargs."""
        self.webapp.update(_signal=False, **kw)

    def set_reviewed(self):
        """Sets reviewed timestamp on version."""
        self.version.update(_signal=False, reviewed=datetime.now())

    def set_files(self, status, files, hide_disabled_file=False):
        """Change the files to be the new status and hide as appropriate."""
        for file in files:
            file.update(_signal=False, datestatuschanged=datetime.now(),
                        reviewed=datetime.now(), status=status)
            if hide_disabled_file:
                file.hide_disabled_file()

    def create_note(self, action):
        """
        Permissions default to developers + reviewers + Mozilla contacts.
        For escalation/comment, exclude the developer from the conversation.
        """
        details = {'comments': self.data['comments'],
                   'reviewtype': self.review_type}
        if self.files:
            details['files'] = [f.id for f in self.files]

        tested = self.get_tested()  # You really should...
        if tested:
            self.data['comments'] += '\n\n%s' % tested

        # Commbadge (the future).
        note_type = comm.ACTION_MAP(action.id)
        self.comm_thread, self.comm_note = create_comm_note(
            self.webapp, self.version, self.request.user,
            self.data['comments'], note_type=note_type,
            attachments=self.attachment_formset)

        # ActivityLog (ye olde).
        mkt.log(action, self.webapp, self.version, user=self.user,
                created=datetime.now(), details=details)

    def get_tested(self):
        """
        Get string indicating devices/browsers used by reviewer to test.
        Will be automatically attached to the note body.
        """
        tested_on_text = []
        if not self.testedon_formset:
            return ''
        for form in self.testedon_formset.forms:
            if form.cleaned_data:
                dtype = form.cleaned_data.get('device_type', None)
                device = form.cleaned_data.get('device', None)
                version = form.cleaned_data.get('version', None)

                if device and version:
                    text = ('%s platform on %s with version %s' %
                            (dtype, device, version))
                elif device and not version:
                    text = '%s platform on %s' % (dtype, device)
                elif not device and version:
                    text = '%s with version %s' % (dtype, version)
                else:
                    text = dtype
                if text:
                    tested_on_text.append(text)
        if not len(tested_on_text):
            return ''
        else:
            return 'Tested on ' + '; '.join(tested_on_text)


class ReviewApp(ReviewBase):

    def set_data(self, data):
        self.data = data
        self.files = self.version.files.all()

    def process_approve(self):
        """
        Handle the approval of apps and/or files.
        """
        if self.webapp.has_incomplete_status():
            # Failsafe.
            return

        # Hold onto the status before we change it.
        status = self.webapp.status
        if self.webapp.publish_type == mkt.PUBLISH_IMMEDIATE:
            self._process_public(mkt.STATUS_PUBLIC)
        elif self.webapp.publish_type == mkt.PUBLISH_HIDDEN:
            self._process_public(mkt.STATUS_UNLISTED)
        else:
            self._process_private()

        # Note: Post save signals shouldn't happen here. All the set_*()
        # methods pass _signal=False to prevent them from being sent. They are
        # manually triggered in the view after the transaction is committed to
        # avoid multiple indexing tasks getting fired with stale data.
        #
        # This does mean that we need to call update_version() manually to get
        # the webapp in the correct state before updating names. We do that,
        # passing _signal=False again to prevent it from sending
        # 'version_changed'. The post_save() that happen in the view will
        # call it without that parameter, sending 'version_changed' normally.
        self.webapp.update_version(_signal=False)
        if self.webapp.is_packaged:
            self.webapp.update_name_from_package_manifest()
        self.webapp.update_supported_locales()
        self.webapp.resend_version_changed_signal = True

        if self.in_escalate:
            EscalationQueue.objects.filter(webapp=self.webapp).delete()

        # Clear priority_review flag on approval - its not persistant.
        if self.webapp.priority_review:
            self.webapp.update(priority_review=False)

        # Assign reviewer incentive scores.
        return ReviewerScore.award_points(self.request.user, self.webapp,
                                          status)

    def _process_private(self):
        """Make an app private."""
        if self.webapp.has_incomplete_status():
            # Failsafe.
            return

        self.webapp.sign_if_packaged(self.version.pk)

        # If there are no prior PUBLIC versions we set the file status to
        # PUBLIC no matter what ``publish_type`` was chosen since at least one
        # version needs to be PUBLIC when an app is approved to set a
        # ``current_version``.
        if File.objects.filter(version__webapp__pk=self.webapp.pk,
                               status=mkt.STATUS_PUBLIC).count() == 0:
            self.set_files(mkt.STATUS_PUBLIC, self.version.files.all())
        else:
            self.set_files(mkt.STATUS_APPROVED, self.version.files.all())

        if self.webapp.status not in (mkt.STATUS_PUBLIC, mkt.STATUS_UNLISTED):
            self.set_webapp(status=mkt.STATUS_APPROVED,
                            highest_status=mkt.STATUS_APPROVED)
        self.set_reviewed()

        self.create_note(mkt.LOG.APPROVE_VERSION_PRIVATE)

        log.info(u'Making %s approved' % self.webapp)

    def _process_public(self, status):
        """Changes status to a publicly viewable status."""
        if self.webapp.has_incomplete_status():
            # Failsafe.
            return

        self.webapp.sign_if_packaged(self.version.pk)
        # Save files first, because set_webapp checks to make sure there
        # is at least one public file or it won't make the webapp public.
        self.set_files(mkt.STATUS_PUBLIC, self.version.files.all())
        # If app is already an approved status, don't change it when approving
        # a version.
        if self.webapp.status not in mkt.WEBAPPS_APPROVED_STATUSES:
            self.set_webapp(status=status, highest_status=status)
        self.set_reviewed()

        set_storefront_data.delay(self.webapp.pk)

        self.create_note(mkt.LOG.APPROVE_VERSION)

        log.info(u'Making %s public' % self.webapp)

    def process_reject(self):
        """
        Reject an app.
        Changes status to Rejected.
        Creates Rejection note.
        """
        # Hold onto the status before we change it.
        status = self.webapp.status

        self.set_files(mkt.STATUS_DISABLED, self.version.files.all(),
                       hide_disabled_file=True)
        # If this app is not packaged (packaged apps can have multiple
        # versions) or if there aren't other versions with already reviewed
        # files, reject the app also.
        if (not self.webapp.is_packaged or
            not self.webapp.versions.exclude(id=self.version.id)
                .filter(files__status__in=mkt.REVIEWED_STATUSES).exists()):
            self.set_webapp(status=mkt.STATUS_REJECTED)

        if self.in_escalate:
            EscalationQueue.objects.filter(webapp=self.webapp).delete()
        if self.in_rereview:
            RereviewQueue.objects.filter(webapp=self.webapp).delete()

        self.create_note(mkt.LOG.REJECT_VERSION)

        log.info(u'Making %s disabled' % self.webapp)

        # Assign reviewer incentive scores.
        return ReviewerScore.award_points(self.request.user, self.webapp,
                                          status, in_rereview=self.in_rereview)

    def process_request_information(self):
        """Send a message to the authors."""
        self.create_note(mkt.LOG.REQUEST_INFORMATION)
        self.version.update(has_info_request=True)
        log.info(u'Sending reviewer message for %s to authors' % self.webapp)

    def process_escalate(self):
        """
        Ask for escalation for an app (EscalationQueue).
        Doesn't change status.
        Creates Escalation note.
        """
        EscalationQueue.objects.get_or_create(webapp=self.webapp)
        self.create_note(mkt.LOG.ESCALATE_MANUAL)
        log.info(u'Escalated review requested for %s' % self.webapp)

    def process_comment(self):
        """
        Editor comment (not visible to developer).
        Doesn't change status.
        Creates Reviewer Comment note.
        """
        self.version.update(has_editor_comment=True)
        self.create_note(mkt.LOG.COMMENT_VERSION)

    def process_manual_rereview(self):
        """
        Adds the app to the rereview queue.
        Doesn't change status.
        Creates Reviewer Comment note.
        """
        RereviewQueue.objects.get_or_create(webapp=self.webapp)
        self.create_note(mkt.LOG.REREVIEW_MANUAL)
        log.info(u'Re-review manually requested for %s' % self.webapp)

    def process_clear_escalation(self):
        """
        Clear app from escalation queue.
        Doesn't change status.
        Creates Reviewer-only note.
        """
        EscalationQueue.objects.filter(webapp=self.webapp).delete()
        self.create_note(mkt.LOG.ESCALATION_CLEARED)
        log.info(u'Escalation cleared for app: %s' % self.webapp)

    def process_clear_rereview(self):
        """
        Clear app from re-review queue.
        Doesn't change status.
        Creates Reviewer-only note.
        """
        RereviewQueue.objects.filter(webapp=self.webapp).delete()
        self.create_note(mkt.LOG.REREVIEW_CLEARED)
        log.info(u'Re-review cleared for app: %s' % self.webapp)
        # Assign reviewer incentive scores.
        return ReviewerScore.award_points(self.request.user, self.webapp,
                                          self.webapp.status, in_rereview=True)

    def process_disable(self):
        """
        Bans app from Marketplace, clears app from all queues.
        Changes status to Disabled.
        Creates Banned/Disabled note.
        """
        if not acl.action_allowed(self.request, 'Apps', 'Edit'):
            return

        # Disable disables all files, not just those in this version.
        self.set_files(mkt.STATUS_DISABLED,
                       File.objects.filter(version__webapp=self.webapp),
                       hide_disabled_file=True)
        self.webapp.update(status=mkt.STATUS_DISABLED)
        if self.in_escalate:
            EscalationQueue.objects.filter(webapp=self.webapp).delete()
        if self.in_rereview:
            RereviewQueue.objects.filter(webapp=self.webapp).delete()

        set_storefront_data.delay(self.webapp.pk, disable=True)

        self.create_note(mkt.LOG.APP_DISABLED)
        log.info(u'App %s has been banned by a reviewer.' % self.webapp)


class ReviewHelper(object):
    """
    A class that builds enough to render the form back to the user and
    process off to the correct handler.
    """

    def __init__(self, request=None, webapp=None, version=None,
                 attachment_formset=None, testedon_formset=None):
        self.handler = None
        self.required = {}
        self.webapp = webapp
        self.version = version
        self.all_files = version and version.files.all()
        self.attachment_formset = attachment_formset
        self.testedon_formset = testedon_formset
        self.handler = ReviewApp(request, webapp, version,
                                 attachment_formset=self.attachment_formset,
                                 testedon_formset=self.testedon_formset)
        self.review_type = self.handler.review_type
        self.actions = self.get_actions()

    def set_data(self, data):
        self.handler.set_data(data)

    def get_actions(self):
        """Get the appropriate handler based on the action."""
        public = {
            'method': self.handler.process_approve,
            'minimal': False,
            'label': _lazy(u'Approve'),
            'details': _lazy(u'This will approve the app and allow the '
                             u'author(s) to publish it.')}
        reject = {
            'method': self.handler.process_reject,
            'label': _lazy(u'Reject'),
            'minimal': False,
            'details': _lazy(u'This will reject the app, remove it from '
                             u'the review queue and un-publish it if already '
                             u'published.')}
        info = {
            'method': self.handler.process_request_information,
            'label': _lazy(u'Message developer'),
            'minimal': True,
            'details': _lazy(u'This will send the author(s) - and other '
                             u'thread subscribers - a message. This will not '
                             u'change the app\'s status.')}
        escalate = {
            'method': self.handler.process_escalate,
            'label': _lazy(u'Escalate'),
            'minimal': True,
            'details': _lazy(u'Flag this app for an admin to review. The '
                             u'comments are sent to the admins, '
                             u'not the author(s).')}
        comment = {
            'method': self.handler.process_comment,
            'label': _lazy(u'Private comment'),
            'minimal': True,
            'details': _lazy(u'Make a private reviewer comment on this app. '
                             u'The message won\'t be visible to the '
                             u'author(s), and no notification will be sent '
                             u'them.')}
        manual_rereview = {
            'method': self.handler.process_manual_rereview,
            'label': _lazy(u'Request Re-review'),
            'minimal': True,
            'details': _lazy(u'Add this app to the re-review queue. Any '
                             u'comments here won\'t be visible to the '
                             u'author(s), and no notification will be sent to'
                             u'them.')}
        clear_escalation = {
            'method': self.handler.process_clear_escalation,
            'label': _lazy(u'Clear Escalation'),
            'minimal': True,
            'details': _lazy(u'Clear this app from the escalation queue. The '
                             u'author(s) will get no email or see comments '
                             u'here.')}
        clear_rereview = {
            'method': self.handler.process_clear_rereview,
            'label': _lazy(u'Clear Re-review'),
            'minimal': True,
            'details': _lazy(u'Clear this app from the re-review queue. The '
                             u'author(s) will get no email or see comments '
                             u'here.')}
        disable = {
            'method': self.handler.process_disable,
            'label': _lazy(u'Ban app'),
            'minimal': True,
            'details': _lazy(u'Ban the app from Marketplace. Similar to '
                             u'Reject but the author(s) can\'t resubmit. To '
                             u'only be used in extreme cases.')}

        actions = OrderedDict()

        if not self.version:
            # Return early if there is no version, this app is incomplete.
            return actions

        file_status = self.version.files.values_list('status', flat=True)
        multiple_versions = (File.objects.exclude(version=self.version)
                                         .filter(
                                             version__webapp=self.webapp,
                                             status__in=mkt.REVIEWED_STATUSES)
                                         .exists())

        show_privileged = (not self.version.is_privileged or
                           acl.action_allowed(self.handler.request, 'Apps',
                                              'ReviewPrivileged'))

        # Public.
        if ((self.webapp.is_packaged and
             mkt.STATUS_PUBLIC not in file_status and show_privileged) or
            (not self.webapp.is_packaged and
             self.webapp.status != mkt.STATUS_PUBLIC)):
            actions['public'] = public

        # Reject.
        if self.webapp.is_packaged and show_privileged:
            # Packaged apps reject the file only, or the app itself if there's
            # only a single version.
            if (not multiple_versions and
                self.webapp.status not in [mkt.STATUS_REJECTED,
                                           mkt.STATUS_DISABLED]):
                actions['reject'] = reject
            elif multiple_versions and mkt.STATUS_DISABLED not in file_status:
                actions['reject'] = reject
        elif not self.webapp.is_packaged:
            # Hosted apps reject the app itself.
            if self.webapp.status not in [mkt.STATUS_REJECTED,
                                          mkt.STATUS_DISABLED]:
                actions['reject'] = reject

        # Ban/Disable.
        if (acl.action_allowed(self.handler.request, 'Apps', 'Edit') and (
                self.webapp.status != mkt.STATUS_DISABLED or
                mkt.STATUS_DISABLED not in file_status)):
            actions['disable'] = disable

        # Clear re-review.
        if self.handler.in_rereview:
            actions['clear_rereview'] = clear_rereview
        else:
            # Manual re-review.
            actions['manual_rereview'] = manual_rereview

        # Clear escalation.
        if self.handler.in_escalate:
            actions['clear_escalation'] = clear_escalation
        else:
            # Escalate.
            actions['escalate'] = escalate

        # Request info and comment are always shown.
        actions['info'] = info
        actions['comment'] = comment

        return actions

    def process(self):
        """Call handler."""
        action = self.handler.data.get('action', '')
        if not action:
            raise NotImplementedError
        return self.actions[action]['method']()


def clean_sort_param(request, date_sort='created'):
    """
    Handles empty and invalid values for sort and sort order.
    'created' by ascending is the default ordering.
    """
    sort = request.GET.get('sort', date_sort)
    order = request.GET.get('order', 'asc')

    if sort not in ('name', 'created', 'nomination'):
        sort = date_sort
    if order not in ('desc', 'asc'):
        order = 'asc'
    return sort, order


def clean_sort_param_es(request, date_sort='created'):
    """
    Handles empty and invalid values for sort and sort order.
    'created' by ascending is the default ordering.
    """
    sort_map = {
        'name': 'name_sort',
        'nomination': 'latest_version.nomination_date',
    }
    sort = request.GET.get('sort', date_sort)
    order = request.GET.get('order', 'asc')

    if sort not in ('name', 'created', 'nomination'):
        sort = date_sort
    sort = sort_map.get(sort, date_sort)
    if order not in ('desc', 'asc'):
        order = 'asc'
    return sort, order


def create_sort_link(pretty_name, sort_field, get_params, sort, order):
    """Generate table header sort links.

    pretty_name -- name displayed on table header
    sort_field -- name of the sort_type GET parameter for the column
    get_params -- additional get_params to include in the sort_link
    sort -- the current sort type
    order -- the current sort order
    """
    get_params.append(('sort', sort_field))

    if sort == sort_field and order == 'asc':
        # Have link reverse sort order to desc if already sorting by desc.
        get_params.append(('order', 'desc'))
    else:
        # Default to ascending.
        get_params.append(('order', 'asc'))

    # Show little sorting sprite if sorting by this field.
    url_class = ''
    if sort == sort_field:
        url_class = ' class="sort-icon ed-sprite-sort-%s"' % order

    return u'<a href="?%s"%s>%s</a>' % (urllib.urlencode(get_params, True),
                                        url_class, pretty_name)


class AppsReviewing(object):
    """
    Class to manage the list of apps a reviewer is currently reviewing.

    Data is stored in memcache.
    """

    def __init__(self, request):
        self.request = request
        self.user_id = request.user.id
        self.key = '%s:myapps:%s' % (settings.CACHE_PREFIX, self.user_id)

    def get_apps(self):
        ids = []
        my_apps = cache.get(self.key)
        if my_apps:
            for id in my_apps.split(','):
                valid = cache.get(
                    '%s:review_viewing:%s' % (settings.CACHE_PREFIX, id))
                if valid and valid == self.user_id:
                    ids.append(id)

        apps = []
        for app in Webapp.objects.filter(id__in=ids):
            apps.append({
                'app': app,
                'app_attrs': json.dumps(
                    product_as_dict(self.request, app, False, 'reviewer'),
                    cls=JSONEncoder),
            })
        return apps

    def add(self, webapp_id):
        my_apps = cache.get(self.key)
        if my_apps:
            apps = my_apps.split(',')
        else:
            apps = []
        apps.append(webapp_id)
        cache.set(self.key, ','.join(map(str, set(apps))),
                  mkt.EDITOR_VIEWING_INTERVAL * 2)


def log_reviewer_action(webapp, user, msg, action, **kwargs):
    create_comm_note(webapp, webapp.latest_version, user, msg,
                     note_type=comm.ACTION_MAP(action.id))
    mkt.log(action, webapp, webapp.latest_version, details={'comments': msg},
            **kwargs)


class ReviewersQueuesHelper(object):
    def __init__(self, request=None, use_es=False):
        self.request = request
        self.use_es = use_es

    @cached_property
    def excluded_ids(self):
        # We need to exclude Escalated Apps from almost all queries, so store
        # the result once.
        return self.get_escalated_queue().values_list('webapp', flat=True)

    def get_escalated_queue(self):
        if self.use_es:
            must = [
                es_filter.Term(is_disabled=False),
                es_filter.Term(is_escalated=True),
            ]
            return WebappIndexer.search().filter('bool', must=must)

        return EscalationQueue.objects.filter(
            webapp__disabled_by_user=False)

    def get_pending_queue(self):
        if self.use_es:
            must = [
                es_filter.Term(status=mkt.STATUS_PENDING),
                es_filter.Term(**{'latest_version.status':
                                  mkt.STATUS_PENDING}),
                es_filter.Term(is_escalated=False),
                es_filter.Term(is_disabled=False),
            ]
            return WebappIndexer.search().filter('bool', must=must)

        return (Version.objects.filter(
            files__status=mkt.STATUS_PENDING,
            webapp__disabled_by_user=False,
            webapp__status=mkt.STATUS_PENDING)
            .exclude(webapp__id__in=self.excluded_ids)
            .order_by('nomination', 'created')
            .select_related('webapp', 'files').no_transforms())

    def get_rereview_queue(self):
        if self.use_es:
            must = [
                es_filter.Term(is_rereviewed=True),
                es_filter.Term(is_disabled=False),
                es_filter.Term(is_escalated=False),
            ]
            return WebappIndexer.search().filter('bool', must=must)

        return (RereviewQueue.objects.
                filter(webapp__disabled_by_user=False).
                exclude(webapp__in=self.excluded_ids))

    def get_updates_queue(self):
        if self.use_es:
            must = [
                es_filter.Terms(status=mkt.WEBAPPS_APPROVED_STATUSES),
                es_filter.Term(**{'latest_version.status':
                                  mkt.STATUS_PENDING}),
                es_filter.Terms(app_type=[mkt.WEBAPP_PACKAGED,
                                          mkt.WEBAPP_PRIVILEGED]),
                es_filter.Term(is_disabled=False),
                es_filter.Term(is_escalated=False),
            ]
            return WebappIndexer.search().filter('bool', must=must)

        return (Version.objects.filter(
            # Note: this will work as long as we disable files of existing
            # unreviewed versions when a new version is uploaded.
            files__status=mkt.STATUS_PENDING,
            webapp__disabled_by_user=False,
            webapp__is_packaged=True,
            webapp__status__in=mkt.WEBAPPS_APPROVED_STATUSES)
            .exclude(webapp__id__in=self.excluded_ids)
            .order_by('nomination', 'created')
            .select_related('webapp', 'files').no_transforms())

    def get_moderated_queue(self):
        return (Review.objects
                .exclude(Q(webapp__isnull=True) | Q(reviewflag__isnull=True))
                .exclude(webapp__status=mkt.STATUS_DELETED)
                .filter(editorreview=True)
                .order_by('reviewflag__created'))

    def get_abuse_queue(self):
        report_ids = (AbuseReport.objects
                      .exclude(webapp__isnull=True)
                      .exclude(webapp__status=mkt.STATUS_DELETED)
                      .filter(read=False)
                      .select_related('webapp')
                      .values_list('webapp', flat=True))

        return Webapp.objects.filter(id__in=report_ids).order_by('created')

    def get_abuse_queue_websites(self):
        report_ids = (AbuseReport.objects
                      .exclude(website__isnull=True)
                      .exclude(website__status=mkt.STATUS_DELETED)
                      .filter(read=False)
                      .select_related('website')
                      .values_list('website', flat=True))

        return Website.objects.filter(id__in=report_ids).order_by('created')

    def sort(self, qs, date_sort='created'):
        """Given a queue queryset, return the sorted version."""
        if self.use_es:
            return self._do_sort_es(qs, date_sort)

        if qs.model == Webapp:
            return self._do_sort_webapp(qs, date_sort)

        return self._do_sort_queue_obj(qs, date_sort)

    def _do_sort_webapp(self, qs, date_sort):
        """
        Column sorting logic based on request GET parameters.
        """
        sort_type, order = clean_sort_param(self.request, date_sort=date_sort)
        order_by = ('-' if order == 'desc' else '') + sort_type

        # Sort.
        if sort_type == 'name':
            # Sorting by name translation.
            return order_by_translation(qs, order_by)

        else:
            return qs.order_by('-priority_review', order_by)

    def _do_sort_queue_obj(self, qs, date_sort):
        """
        Column sorting logic based on request GET parameters.
        Deals with objects with joins on the Webapp (e.g. RereviewQueue,
        Version). Returns qs of apps.
        """
        sort_type, order = clean_sort_param(self.request, date_sort=date_sort)
        sort_str = sort_type

        if sort_type not in [date_sort, 'name']:
            sort_str = 'webapp__' + sort_type

        # sort_str includes possible joins when ordering.
        # sort_type is the name of the field to sort on without desc/asc
        # markers. order_by is the name of the field to sort on with desc/asc
        # markers.
        order_by = ('-' if order == 'desc' else '') + sort_str

        # Sort.
        if sort_type == 'name':
            # Sorting by name translation through an webapp foreign key.
            return order_by_translation(
                Webapp.objects.filter(
                    id__in=qs.values_list('webapp', flat=True)), order_by)

        # Convert sorted queue object queryset to sorted app queryset.
        sorted_app_ids = (qs.order_by('-webapp__priority_review', order_by)
                            .values_list('webapp', flat=True))
        qs = Webapp.objects.filter(id__in=sorted_app_ids)
        return manual_order(qs, sorted_app_ids, 'webapps.id')

    def _do_sort_es(self, qs, date_sort):
        sort_type, order = clean_sort_param_es(self.request,
                                               date_sort=date_sort)
        order_by = ('-' if order == 'desc' else '') + sort_type

        return qs.sort(order_by)
