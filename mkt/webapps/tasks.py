import datetime
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.urlresolvers import reverse
from django.template import Context, loader
from django.test.client import RequestFactory

import pytz
import requests
from celery import chord
from celery.exceptions import RetryTaskError
from celery import task
from requests.exceptions import RequestException
from tower import ugettext as _

import mkt
from lib.post_request_task.task import task as post_request_task
from mkt.abuse.models import AbuseReport
from mkt.constants.regions import RESTOFWORLD
from mkt.developers.models import ActivityLog, AppLog
from mkt.developers.tasks import _fetch_manifest, validator
from mkt.files.models import FileUpload
from mkt.reviewers.models import EscalationQueue, RereviewQueue
from mkt.site.decorators import set_task_user, use_master
from mkt.site.helpers import absolutify
from mkt.site.mail import send_mail_jinja
from mkt.site.storage_utils import (copy_to_storage, local_storage,
                                    private_storage, public_storage,
                                    walk_storage)
from mkt.site.utils import JSONEncoder, chunked
from mkt.users.models import UserProfile
from mkt.users.utils import get_task_user
from mkt.webapps.indexers import WebappIndexer
from mkt.webapps.models import Preview, Webapp
from mkt.webapps.utils import get_locale_properties


task_log = logging.getLogger('z.task')


@task
@use_master
def version_changed(addon_id, **kw):
    update_last_updated(addon_id)


def update_last_updated(addon_id):
    qs = Webapp._last_updated_queries()
    if not Webapp.objects.filter(pk=addon_id).exists():
        task_log.info(
            '[1@None] Updating last updated for %s failed, no addon found'
            % addon_id)
        return

    task_log.info('[1@None] Updating last updated for %s.' % addon_id)

    res = (qs.filter(pk=addon_id)
             .using('default')
             .values_list('id', 'last_updated'))
    if res:
        pk, t = res[0]
        Webapp.objects.filter(pk=pk).update(last_updated=t)


@task
def delete_preview_files(id, **kw):
    task_log.info('[1@None] Removing preview with id of %s.' % id)

    p = Preview(id=id)
    for f in (p.thumbnail_path, p.image_path):
        try:
            public_storage.delete(f)
        except Exception, e:
            task_log.error('Error deleting preview file (%s): %s' % (f, e))


def _get_content_hash(content):
    return 'sha256:%s' % hashlib.sha256(content).hexdigest()


def _log(webapp, message, rereview=False, exc_info=False):
    if rereview:
        message = u'(Re-review) ' + unicode(message)
    task_log.info(u'[Webapp:%s] %s' % (webapp, unicode(message)),
                  exc_info=exc_info)


@task
@use_master
def update_manifests(ids, **kw):
    retry_secs = 3600
    task_log.info('[%s@%s] Update manifests.' %
                  (len(ids), update_manifests.rate_limit))
    check_hash = kw.pop('check_hash', True)
    retries = kw.pop('retries', {})
    # Since we'll be logging the updated manifest change to the users log,
    # we'll need to log in as user.
    mkt.set_user(get_task_user())

    for id in ids:
        _update_manifest(id, check_hash, retries)
    if retries:
        try:
            update_manifests.retry(args=(retries.keys(),),
                                   kwargs={'check_hash': check_hash,
                                           'retries': retries},
                                   eta=datetime.datetime.now() +
                                   datetime.timedelta(seconds=retry_secs),
                                   max_retries=5)
        except RetryTaskError:
            _log(id, 'Retrying task in %d seconds.' % retry_secs)

    return retries


def notify_developers_of_failure(app, error_message, has_link=False):
    if (app.status not in mkt.WEBAPPS_APPROVED_STATUSES or
            RereviewQueue.objects.filter(addon=app).exists()):
        # If the app isn't public, or has already been reviewed, we don't
        # want to send the mail.
        return

    # FIXME: how to integrate with commbadge?

    for author in app.authors.all():
        context = {
            'error_message': error_message,
            'SITE_URL': settings.SITE_URL,
            'SUPPORT_GROUP': settings.SUPPORT_GROUP,
            'has_link': has_link
        }
        to = [author.email]
        with author.activate_lang():
            # Re-fetch the app to get translations in the right language.
            context['app'] = Webapp.objects.get(pk=app.pk)

            subject = _(u'Issue with your app "{app}" on the Firefox '
                        u'Marketplace').format(**context)
            send_mail_jinja(subject,
                            'webapps/emails/update_manifest_failure.txt',
                            context, recipient_list=to)


def _update_manifest(id, check_hash, failed_fetches):
    webapp = Webapp.objects.get(pk=id)
    version = webapp.versions.latest()
    file_ = version.files.latest()

    _log(webapp, u'Fetching webapp manifest')
    if not file_:
        _log(webapp, u'Ignoring, no existing file')
        return

    # Fetch manifest, catching and logging any exception.
    try:
        content = _fetch_manifest(webapp.manifest_url)
    except Exception, e:
        msg = u'Failed to get manifest from %s. Error: %s' % (
            webapp.manifest_url, e)
        failed_fetches[id] = failed_fetches.get(id, 0) + 1
        if failed_fetches[id] == 3:
            # This is our 3rd attempt, let's send the developer(s) an email to
            # notify him of the failures.
            notify_developers_of_failure(webapp, u'Validation errors:\n' + msg)
        elif failed_fetches[id] >= 4:
            # This is our 4th attempt, we should already have notified the
            # developer(s). Let's put the app in the re-review queue.
            _log(webapp, msg, rereview=True, exc_info=True)
            if webapp.status in mkt.WEBAPPS_APPROVED_STATUSES:
                RereviewQueue.flag(webapp, mkt.LOG.REREVIEW_MANIFEST_CHANGE,
                                   msg)
            del failed_fetches[id]
        else:
            _log(webapp, msg, rereview=False, exc_info=True)
        return

    # Check hash.
    if check_hash:
        hash_ = _get_content_hash(content)
        if file_.hash == hash_:
            _log(webapp, u'Manifest the same')
            return
        _log(webapp, u'Manifest different')

    # Validate the new manifest.
    upload = FileUpload.objects.create()
    upload.add_file([content], webapp.manifest_url, len(content))

    validator(upload.pk)

    upload = FileUpload.objects.get(pk=upload.pk)
    if upload.validation:
        v8n = json.loads(upload.validation)
        if v8n['errors']:
            v8n_url = absolutify(reverse(
                'mkt.developers.upload_detail', args=[upload.uuid]))
            msg = u'Validation errors:\n'
            for m in v8n['messages']:
                if m['type'] == u'error':
                    msg += u'* %s\n' % m['message']
            msg += u'\nValidation Result:\n%s' % v8n_url
            _log(webapp, msg, rereview=True)
            if webapp.status in mkt.WEBAPPS_APPROVED_STATUSES:
                notify_developers_of_failure(webapp, msg, has_link=True)
                RereviewQueue.flag(webapp, mkt.LOG.REREVIEW_MANIFEST_CHANGE,
                                   msg)
            return
    else:
        _log(webapp,
             u'Validation for upload UUID %s has no result' % upload.uuid)

    # Get the old manifest before we overwrite it.
    new = json.loads(content)
    old = webapp.get_manifest_json(file_)

    # New manifest is different and validates, update version/file.
    try:
        webapp.manifest_updated(content, upload)
    except:
        _log(webapp, u'Failed to create version', exc_info=True)

    # Check for any name changes at root and in locales. If any were added or
    # updated, send to re-review queue.
    msg = []
    rereview = False
    # Some changes require a new call to IARC's SET_STOREFRONT_DATA.
    iarc_storefront = False

    if old and old.get('name') != new.get('name'):
        rereview = True
        iarc_storefront = True
        msg.append(u'Manifest name changed from "%s" to "%s".' % (
            old.get('name'), new.get('name')))

    new_version = webapp.versions.latest()
    # Compare developer_name between old and new version using the property
    # that fallbacks to the author name instead of using the db field directly.
    # This allows us to avoid forcing a re-review on old apps which didn't have
    # developer name in their manifest initially and upload a new version that
    # does, providing that it matches the original author name.
    if version.developer_name != new_version.developer_name:
        rereview = True
        iarc_storefront = True
        msg.append(u'Developer name changed from "%s" to "%s".'
                   % (version.developer_name, new_version.developer_name))

    # Get names in "locales" as {locale: name}.
    locale_names = get_locale_properties(new, 'name', webapp.default_locale)

    # Check changes to default_locale.
    locale_changed = webapp.update_default_locale(new.get('default_locale'))
    if locale_changed:
        msg.append(u'Default locale changed from "%s" to "%s".'
                   % locale_changed)

    # Update names
    crud = webapp.update_names(locale_names)
    if any(crud.values()):
        webapp.save()

    if crud.get('added'):
        rereview = True
        msg.append(u'Locales added: %s' % crud.get('added'))
    if crud.get('updated'):
        rereview = True
        msg.append(u'Locales updated: %s' % crud.get('updated'))

    # Check if supported_locales changed and update if so.
    webapp.update_supported_locales(manifest=new, latest=True)

    if rereview:
        msg = ' '.join(msg)
        _log(webapp, msg, rereview=True)
        if webapp.status in mkt.WEBAPPS_APPROVED_STATUSES:
            RereviewQueue.flag(webapp, mkt.LOG.REREVIEW_MANIFEST_CHANGE, msg)

    if iarc_storefront:
        webapp.set_iarc_storefront_data()


@post_request_task
@use_master
def update_cached_manifests(id, **kw):
    try:
        webapp = Webapp.objects.get(pk=id)
    except Webapp.DoesNotExist:
        _log(id, u'Webapp does not exist')
        return

    if not webapp.is_packaged:
        return

    # Rebuilds the packaged app mini manifest and stores it in cache.
    webapp.get_cached_manifest(force=True)
    _log(webapp, u'Updated cached mini manifest')


@task
@use_master
def update_supported_locales(ids, **kw):
    """
    Task intended to run via command line to update all apps' supported locales
    based on the current version.
    """
    for chunk in chunked(ids, 50):
        for app in Webapp.objects.filter(id__in=chunk):
            try:
                if app.update_supported_locales():
                    _log(app, u'Updated supported locales')
            except Exception:
                _log(app, u'Updating supported locales failed.', exc_info=True)


@post_request_task(acks_late=True)
@use_master
def index_webapps(ids, **kw):
    # DEPRECATED: call WebappIndexer.index_ids directly.
    WebappIndexer.index_ids(ids, no_delay=True)


@post_request_task(acks_late=True)
@use_master
def unindex_webapps(ids, **kw):
    # DEPRECATED: call WebappIndexer.unindexer directly.
    WebappIndexer.unindexer(ids)


@task
def dump_app(id, **kw):
    from mkt.webapps.serializers import AppSerializer
    target_dir = os.path.join(settings.DUMPED_APPS_PATH, 'apps',
                              str(id / 1000))
    target_file = os.path.join(target_dir, str(id) + '.json')

    try:
        obj = Webapp.objects.get(pk=id)
    except Webapp.DoesNotExist:
        task_log.info(u'Webapp does not exist: {0}'.format(id))
        return

    req = RequestFactory().get('/')
    req.user = AnonymousUser()
    req.REGION = RESTOFWORLD

    task_log.info('Dumping app {0} to {1}'.format(id, target_file))
    res = AppSerializer(obj, context={'request': req}).data
    with private_storage.open(target_file, 'w') as fileobj:
        json.dump(res, fileobj, cls=JSONEncoder)
    return target_file


@task(ignore_result=False)
def dump_apps(ids, **kw):
    task_log.info(u'Dumping apps {0} to {1}. [{2}]'
                  .format(ids[0], ids[-1], len(ids)))
    for id in ids:
        dump_app(id)


def rm_directory(path):
    if os.path.exists(path):
        shutil.rmtree(path)


def dump_all_apps_tasks():
    all_pks = (Webapp.objects.visible()
                             .values_list('pk', flat=True)
                             .order_by('pk'))
    return [dump_apps.si(pks) for pks in chunked(all_pks, 100)]


@task
def export_data(name=None):
    today = datetime.datetime.today().strftime('%Y-%m-%d')
    if name is None:
        name = today

    # Clean up the path where we'll store the individual json files from each
    # app dump.
    for dirpath, dirnames, filenames in walk_storage(
            settings.DUMPED_APPS_PATH, storage=private_storage):
        for filename in filenames:
            private_storage.delete(os.path.join(dirpath, filename))
    task_log.info('Cleaning up path {0}'.format(settings.DUMPED_APPS_PATH))

    # Run all dump_apps task in parallel, and once it's done, add extra files
    # and run compression.
    chord(dump_all_apps_tasks(),
          compress_export.si(tarball_name=name, date=today)).apply_async()


def compile_extra_files(target_directory, date):
    # Put some .txt files in place. This is done locally only, it's only useful
    # before the tar command is run.
    context = Context({'date': date, 'url': settings.SITE_URL})
    extra_filenames = ['license.txt', 'readme.txt']
    for extra_filename in extra_filenames:
        template = loader.get_template('webapps/dump/apps/%s' % extra_filename)
        dst = os.path.join(target_directory, extra_filename)
        with local_storage.open(dst, 'w') as fd:
            fd.write(template.render(context))
    return extra_filenames


@task
def compress_export(tarball_name, date):
    # We need a temporary directory on the local filesystem that will contain
    # all files in order to call `tar`.
    local_source_dir = tempfile.mkdtemp()

    apps_dirpath = os.path.join(settings.DUMPED_APPS_PATH, 'apps')

    # In case apps_dirpath is empty, add a dummy file to make the apps
    # directory in the tar archive non-empty. It should not happen in prod, but
    # it's nice to have it to prevent the task from failing entirely.
    with private_storage.open(
            os.path.join(apps_dirpath, '0', '.keep'), 'w') as fd:
        fd.write('.')

    # Now, copy content from private_storage to that temp directory. We don't
    # need to worry about creating the directories locally, the storage class
    # does that for us.
    for dirpath, dirnames, filenames in walk_storage(
            apps_dirpath, storage=private_storage):
        for filename in filenames:
            src_path = os.path.join(dirpath, filename)
            dst_path = os.path.join(
                local_source_dir, 'apps', os.path.basename(dirpath), filename)
            copy_to_storage(
                src_path, dst_path, src_storage=private_storage,
                dst_storage=local_storage)

    # Also add extra files to the temp directory.
    extra_filenames = compile_extra_files(local_source_dir, date)

    # All our files are now present locally, let's generate a local filename
    # that will contain the final '.tar.gz' before it's copied over to
    # public storage.
    local_target_file = tempfile.NamedTemporaryFile(
        suffix='.tgz', prefix='dumped-apps-')

    # tar ALL the things!
    cmd = ['tar', 'czf', local_target_file.name, '-C',
           local_source_dir] + ['apps'] + extra_filenames
    task_log.info(u'Creating dump {0}'.format(local_target_file.name))
    subprocess.call(cmd)

    # Now copy the local tgz to the public storage.
    remote_target_filename = os.path.join(
        settings.DUMPED_APPS_PATH, 'tarballs', '%s.tgz' % tarball_name)
    copy_to_storage(local_target_file.name, remote_target_filename,
                    dst_storage=public_storage)

    # Clean-up.
    local_target_file.close()
    rm_directory(local_source_dir)
    return remote_target_filename


@task(ignore_result=False)
def dump_user_installs(ids, **kw):
    task_log.info(u'Dumping user installs {0} to {1}. [{2}]'
                  .format(ids[0], ids[-1], len(ids)))

    users = (UserProfile.objects.filter(enable_recommendations=True)
             .filter(id__in=ids))
    for user in users:
        hash = user.recommendation_hash
        target_dir = os.path.join(settings.DUMPED_USERS_PATH, 'users', hash[0])
        target_file = os.path.join(target_dir, '%s.json' % hash)

        # Gather data about user.
        installed = []
        zone = pytz.timezone(settings.TIME_ZONE)
        for install in user.installed_set.all():
            try:
                app = install.addon
            except Webapp.DoesNotExist:
                continue

            installed.append({
                'id': app.id,
                'slug': app.app_slug,
                'installed': pytz.utc.normalize(
                    zone.localize(install.created)).strftime(
                        '%Y-%m-%dT%H:%M:%S')
            })

        data = {
            'user': hash,
            'region': user.region,
            'lang': user.lang,
            'installed_apps': installed,
        }

        task_log.info('Dumping user {0} to {1}'.format(user.id, target_file))
        with private_storage.open(target_file, 'w') as fileobj:
            json.dump(data, fileobj, cls=JSONEncoder)


@task
def zip_users(*args, **kw):
    date = datetime.datetime.utcnow().strftime('%Y-%m-%d')
    tarball_name = date

    # We need a temporary directory on the local filesystem that will contain
    # all files in order to call `tar`.
    local_source_dir = tempfile.mkdtemp()

    users_dirpath = os.path.join(settings.DUMPED_USERS_PATH, 'users')

    # In case users_dirpath is empty, add a dummy file to make the users
    # directory in the tar archive non-empty. It should not happen in prod, but
    # it's nice to have it to prevent the task from failing entirely.
    with private_storage.open(
            os.path.join(users_dirpath, '0', '.keep'), 'w') as fd:
        fd.write('.')

    # Now, copy content from private_storage to that temp directory. We don't
    # need to worry about creating the directories locally, the storage class
    # does that for us.
    for dirpath, dirnames, filenames in walk_storage(
            users_dirpath, storage=private_storage):
        for filename in filenames:
            src_path = os.path.join(dirpath, filename)
            dst_path = os.path.join(
                local_source_dir, 'users', os.path.basename(dirpath), filename)
            copy_to_storage(
                src_path, dst_path, src_storage=private_storage,
                dst_storage=local_storage)

    # Put some .txt files in place locally.
    context = Context({'date': date, 'url': settings.SITE_URL})
    extra_filenames = ['license.txt', 'readme.txt']
    for extra_filename in extra_filenames:
        template = loader.get_template('webapps/dump/users/' + extra_filename)
        dst = os.path.join(local_source_dir, extra_filename)
        with local_storage.open(dst, 'w') as fd:
            fd.write(template.render(context))

    # All our files are now present locally, let's generate a local filename
    # that will contain the final '.tar.gz' before it's copied over to
    # public storage.
    local_target_file = tempfile.NamedTemporaryFile(
        suffix='.tgz', prefix='dumped-users-')

    # tar ALL the things!
    cmd = ['tar', 'czf', local_target_file.name, '-C',
           local_source_dir] + ['users'] + extra_filenames
    task_log.info(u'Creating user dump {0}'.format(local_target_file.name))
    subprocess.call(cmd)

    # Now copy the local tgz to the public storage.
    remote_target_filename = os.path.join(
        settings.DUMPED_USERS_PATH, 'tarballs', '%s.tgz' % tarball_name)
    copy_to_storage(local_target_file.name, remote_target_filename,
                    dst_storage=public_storage)

    # Clean-up.
    local_target_file.close()
    rm_directory(local_source_dir)
    return remote_target_filename


class PreGenAPKError(Exception):
    """
    An error encountered while trying to pre-generate an APK.
    """


@task
@use_master
def pre_generate_apk(app_id, **kw):
    app = Webapp.objects.get(pk=app_id)
    manifest_url = app.get_manifest_url()
    task_log.info(u'pre-generating APK for app {a} at {url}'
                  .format(a=app, url=manifest_url))
    if not manifest_url:
        raise PreGenAPKError(u'Webapp {w} has an empty manifest URL'
                             .format(w=app))
    try:
        res = requests.get(
            settings.PRE_GENERATE_APK_URL,
            params={'manifestUrl': manifest_url},
            headers={'User-Agent': settings.MARKETPLACE_USER_AGENT})
        res.raise_for_status()
    except RequestException, exc:
        raise PreGenAPKError(u'Error pre-generating APK for app {a} at {url}; '
                             u'generator={gen} (SSL cert ok?); '
                             u'{e.__class__.__name__}: {e}'
                             .format(a=app, url=manifest_url, e=exc,
                                     gen=settings.PRE_GENERATE_APK_URL))

    # The factory returns a binary APK blob but we don't need it.
    res.close()
    del res


@task
@use_master
def set_storefront_data(app_id, disable=False, **kw):
    """
    Call IARC's SET_STOREFRONT_DATA endpoint.
    """
    try:
        app = Webapp.with_deleted.get(pk=app_id)
    except Webapp.DoesNotExist:
        return

    app.set_iarc_storefront_data(disable=disable)


@task
def delete_logs(items, **kw):
    task_log.info('[%s@%s] Deleting logs'
                  % (len(items), delete_logs.rate_limit))
    ActivityLog.objects.filter(pk__in=items).exclude(
        action__in=mkt.LOG_KEEP).delete()


@task
@set_task_user
def find_abuse_escalations(addon_id, **kw):
    weekago = datetime.date.today() - datetime.timedelta(days=7)
    add_to_queue = True

    for abuse in AbuseReport.recent_high_abuse_reports(1, weekago, addon_id):
        if EscalationQueue.objects.filter(addon=abuse.addon).exists():
            # App is already in the queue, no need to re-add it.
            task_log.info(u'[app:%s] High abuse reports, but already '
                          u'escalated' % abuse.addon)
            add_to_queue = False

        # We have an abuse report... has it been detected and dealt with?
        logs = (AppLog.objects.filter(
            activity_log__action=mkt.LOG.ESCALATED_HIGH_ABUSE.id,
            addon=abuse.addon).order_by('-created'))
        if logs:
            abuse_since_log = AbuseReport.recent_high_abuse_reports(
                1, logs[0].created, addon_id)
            # If no abuse reports have happened since the last logged abuse
            # report, do not add to queue.
            if not abuse_since_log:
                task_log.info(u'[app:%s] High abuse reports, but none since '
                              u'last escalation' % abuse.addon)
                continue

        # If we haven't bailed out yet, escalate this app.
        msg = u'High number of abuse reports detected'
        if add_to_queue:
            EscalationQueue.objects.create(addon=abuse.addon)
        mkt.log(mkt.LOG.ESCALATED_HIGH_ABUSE, abuse.addon,
                abuse.addon.current_version, details={'comments': msg})
        task_log.info(u'[app:%s] %s' % (abuse.addon, msg))
