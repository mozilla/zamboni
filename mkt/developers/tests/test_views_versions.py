import os

from django.conf import settings

import mock
from nose.tools import eq_, ok_
from pyquery import PyQuery as pq

import mkt
import mkt.site.tests
from mkt.comm.models import CommunicationNote
from mkt.constants.applications import DEVICE_TYPES
from mkt.developers.models import ActivityLog, AppLog
from mkt.files.models import File
from mkt.reviewers.models import EscalationQueue
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import (copy_stored_file, local_storage,
                                    private_storage, storage_is_remote)
from mkt.site.tests import user_factory
from mkt.site.utils import app_factory, make_rated, version_factory
from mkt.submit.tests.test_views import BasePackagedAppTest
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps.models import AddonUser, Webapp


class TestVersion(mkt.site.tests.TestCase):
    fixtures = fixture('group_admin', 'user_999', 'user_admin',
                       'user_admin_group', 'webapp_337141')

    def setUp(self):
        self.login('admin@mozilla.com')
        self.webapp = self.get_webapp()
        self.url = self.webapp.get_dev_url('versions')

    def get_webapp(self):
        return Webapp.objects.get(id=337141)

    def test_nav_link(self):
        r = self.client.get(self.url)
        eq_(pq(r.content)('.edit-addon-nav li.selected a').attr('href'),
            self.url)

    def test_items(self):
        doc = pq(self.client.get(self.url).content)
        eq_(doc('#version-status').length, 1)
        eq_(doc('#version-list').length, 0)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#modal-delete').length, 1)
        eq_(doc('#modal-disable').length, 1)
        eq_(doc('#modal-delete-version').length, 0)

    def test_delete_link(self):
        # Hard "Delete App" link should be visible for only incomplete apps.
        self.webapp.update(status=mkt.STATUS_NULL)
        doc = pq(self.client.get(self.url).content)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#modal-delete').length, 1)

    def test_pending(self):
        self.webapp.update(status=mkt.STATUS_PENDING)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('#version-status .status-pending').length, 1)
        eq_(doc('#rejection').length, 0)

    def test_public(self):
        eq_(self.webapp.status, mkt.STATUS_PUBLIC)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('#version-status .status-public').length, 1)
        eq_(doc('#rejection').length, 0)

    def test_blocked(self):
        self.webapp.update(status=mkt.STATUS_BLOCKED)
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('#version-status .status-blocked').length, 1)
        eq_(doc('#rejection').length, 0)
        assert 'blocked by a site administrator' in doc.text()

    def test_rejected(self):
        comments = "oh no you di'nt!!"
        mkt.set_user(UserProfile.objects.get(email='admin@mozilla.com'))
        mkt.log(mkt.LOG.REJECT_VERSION, self.webapp,
                self.webapp.current_version, user_id=999,
                details={'comments': comments, 'reviewtype': 'pending'})
        self.webapp.update(status=mkt.STATUS_REJECTED)
        make_rated(self.webapp)
        (self.webapp.versions.latest()
                             .all_files[0].update(status=mkt.STATUS_DISABLED))

        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)('#version-status')
        eq_(doc('.status-rejected').length, 1)
        eq_(doc('#rejection').length, 1)
        eq_(doc('#rejection blockquote').text(), comments)

        my_reply = 'fixed just for u, brah'
        r = self.client.post(self.url, {'notes': my_reply,
                                        'resubmit-app': ''})
        self.assert3xx(r, self.url, 302)

        webapp = self.get_webapp()
        eq_(webapp.status, mkt.STATUS_PENDING,
            'Reapplied apps should get marked as pending')
        eq_(webapp.versions.latest().all_files[0].status, mkt.STATUS_PENDING,
            'Files for reapplied apps should get marked as pending')
        action = mkt.LOG.WEBAPP_RESUBMIT
        assert AppLog.objects.filter(
            addon=webapp, activity_log__action=action.id).exists(), (
                "Didn't find `%s` action in logs." % action.short)

    def test_no_ratings_no_resubmit(self):
        self.webapp.update(status=mkt.STATUS_REJECTED)
        r = self.client.post(self.url, {'notes': 'lol',
                                        'resubmit-app': ''})
        eq_(r.status_code, 403)

        self.webapp.content_ratings.create(ratings_body=0, rating=0)
        r = self.client.post(self.url, {'notes': 'lol',
                                        'resubmit-app': ''})
        self.assert3xx(r, self.webapp.get_dev_url('versions'))

    def test_comm_thread_after_resubmission(self):
        self.webapp.update(status=mkt.STATUS_REJECTED)
        make_rated(self.webapp)
        mkt.set_user(UserProfile.objects.get(email='admin@mozilla.com'))
        (self.webapp.versions.latest()
                             .all_files[0].update(status=mkt.STATUS_DISABLED))
        my_reply = 'no give up'
        self.client.post(self.url, {'notes': my_reply,
                                    'resubmit-app': ''})
        notes = CommunicationNote.objects.all()
        eq_(notes.count(), 1)
        eq_(notes[0].body, my_reply)

    def test_rejected_packaged(self):
        self.webapp.update(is_packaged=True)
        comments = "oh no you di'nt!!"
        mkt.set_user(UserProfile.objects.get(email='admin@mozilla.com'))
        mkt.log(mkt.LOG.REJECT_VERSION, self.webapp,
                self.webapp.current_version, user_id=999,
                details={'comments': comments, 'reviewtype': 'pending'})
        self.webapp.update(status=mkt.STATUS_REJECTED)
        (self.webapp.versions.latest()
                             .all_files[0].update(status=mkt.STATUS_DISABLED))

        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content)('#version-status')
        eq_(doc('.status-rejected').length, 1)
        eq_(doc('#rejection').length, 1)
        eq_(doc('#rejection blockquote').text(), comments)


class BaseAddVersionTest(BasePackagedAppTest):
    def setUp(self):
        super(BaseAddVersionTest, self).setUp()
        self.app = app_factory(complete=True, is_packaged=True,
                               app_domain='app://hy.fr',
                               version_kw=dict(version='1.0'))
        self.url = self.app.get_dev_url('versions')
        self.user = UserProfile.objects.get(email='regular@mozilla.com')
        AddonUser.objects.create(user=self.user, addon=self.app)

    def _post(self, expected_status=200):
        res = self.client.post(self.url, {'upload': self.upload.pk,
                                          'upload-version': ''})
        eq_(res.status_code, expected_status)
        return res


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestAddVersion(BaseAddVersionTest):

    def setUp(self):
        super(TestAddVersion, self).setUp()

        # Update version to be < 1.0 so we don't throw validation errors.
        self.app.current_version.update(version='0.9',
                                        created=self.days_ago(1))

    def test_post(self):
        self._post(302)
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)

    def test_unique_version(self):
        self.app.current_version.update(version='1.0')
        res = self._post(200)
        self.assertFormError(res, 'upload_form', 'upload',
                             'Version 1.0 already exists.')

    def test_origin_changed(self):
        for origin in (None, 'app://yo.lo'):
            self.app.update(app_domain=origin)
            res = self._post(200)
            self.assertFormError(res, 'upload_form', 'upload',
                                 'Changes to "origin" are not allowed.')

    def test_pending_on_new_version(self):
        # Test app rejection, then new version, updates app status to pending.
        self.app.update(status=mkt.STATUS_REJECTED)
        files = File.objects.filter(version__addon=self.app)
        files.update(status=mkt.STATUS_DISABLED)
        self._post(302)
        self.app.reload()
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)
        eq_(self.app.status, mkt.STATUS_PENDING)

    @mock.patch('mkt.developers.views.run_validator')
    def test_prefilled_features(self, run_validator_):
        run_validator_.return_value = '{"feature_profile": ["apps", "audio"]}'

        # All features should be disabled.
        features = self.app.current_version.features.to_dict()
        eq_(any(features.values()), False)

        self._post(302)

        # In this new version we should be prechecked new ones.
        features = self.app.versions.latest().features.to_dict()
        for key, feature in features.iteritems():
            eq_(feature, key in ('has_apps', 'has_audio'))

    def test_blocklist_on_new_version(self):
        # Test app blocked, then new version, doesn't update app status, and
        # app shows up in escalation queue.
        self.app.update(status=mkt.STATUS_BLOCKED)
        files = File.objects.filter(version__addon=self.app)
        files.update(status=mkt.STATUS_DISABLED)
        self._post(302)
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)
        self.app.update_status()
        eq_(self.app.status, mkt.STATUS_BLOCKED)
        assert EscalationQueue.objects.filter(addon=self.app).exists(), (
            'App not in escalation queue')

    def test_new_version_when_incomplete(self):
        self.app.update(status=mkt.STATUS_NULL)
        files = File.objects.filter(version__addon=self.app)
        files.update(status=mkt.STATUS_DISABLED)
        self._post(302)
        self.app.reload()
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)
        eq_(self.app.status, mkt.STATUS_PENDING)

    def test_vip_app_added_to_escalation_queue(self):
        self.app.update(vip_app=True)
        self._post(302)

        assert EscalationQueue.objects.filter(addon=self.app).exists(), (
            'VIP App not in escalation queue')


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestAddVersionPrereleasePermissions(BaseAddVersionTest):
    @property
    def package(self):
        return self.packaged_app_path('prerelease.zip')

    def test_escalate_on_prerelease_permissions(self):
        """Test that apps that use prerelease permissions are escalated."""
        user_factory(email=settings.NOBODY_EMAIL_ADDRESS)
        self.app.current_version.update(version='0.9',
                                        created=self.days_ago(1))
        ok_(not EscalationQueue.objects.filter(addon=self.app).exists(),
            'App in escalation queue')
        self._post(302)
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)
        self.app.update_status()
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        ok_(EscalationQueue.objects.filter(addon=self.app).exists(),
            'App not in escalation queue')


@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestAddVersionNoPermissions(BaseAddVersionTest):
    @property
    def package(self):
        return self.packaged_app_path('no_permissions.zip')

    def test_no_escalate_on_blank_permissions(self):
        """Test that apps that do not use permissions are not escalated."""
        self.app.current_version.update(version='0.9',
                                        created=self.days_ago(1))
        ok_(not EscalationQueue.objects.filter(addon=self.app).exists(),
            'App in escalation queue')
        self._post(302)
        version = self.app.versions.latest()
        eq_(version.version, '1.0')
        eq_(version.all_files[0].status, mkt.STATUS_PENDING)
        self.app.update_status()
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        ok_(not EscalationQueue.objects.filter(addon=self.app).exists(),
            'App in escalation queue')


class TestVersionPackaged(mkt.site.tests.WebappTestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        super(TestVersionPackaged, self).setUp()
        self.login('steamcube@mozilla.com')
        self.app.update(is_packaged=True)
        self.app = self.get_app()
        # Needed for various status checking routines on fully complete apps.
        make_rated(self.app)
        if not self.app.categories:
            self.app.update(categories=['utilities'])
        self.app.addondevicetype_set.create(device_type=DEVICE_TYPES.keys()[0])
        self.app.previews.create()

        self.url = self.app.get_dev_url('versions')
        self.delete_url = self.app.get_dev_url('versions.delete')

    def test_items_packaged(self):
        doc = pq(self.client.get(self.url).content)
        eq_(doc('#version-status').length, 1)
        eq_(doc('#version-list').length, 1)
        eq_(doc('#delete-addon').length, 1)
        eq_(doc('#modal-delete').length, 1)
        eq_(doc('#modal-disable').length, 1)
        eq_(doc('#modal-delete-version').length, 1)

    def test_version_list_packaged(self):
        self.app.update(is_packaged=True)
        version_factory(addon=self.app, version='2.0',
                        file_kw=dict(status=mkt.STATUS_PENDING))
        self.app = self.get_app()
        doc = pq(self.client.get(self.url).content)
        eq_(doc('#version-status').length, 1)
        eq_(doc('#version-list tbody tr').length, 2)
        # 1 pending and 1 public.
        eq_(doc('#version-list span.status-pending').length, 1)
        eq_(doc('#version-list span.status-public').length, 1)
        # Check version strings and order of versions.
        eq_(map(lambda x: x.text, doc('#version-list h4 a')),
            ['2.0', '1.0'])
        # There should be 2 delete buttons.
        eq_(doc('#version-list a.delete-version.button').length, 2)
        # Check download url.
        eq_(doc('#version-list a.download').eq(0).attr('href'),
            self.app.versions.all()[0].all_files[0].get_url_path(''))
        eq_(doc('#version-list a.download').eq(1).attr('href'),
            self.app.versions.all()[1].all_files[0].get_url_path(''))

    def test_delete_version_xss(self):
        version = self.app.versions.latest()
        version.update(version='<script>alert("xss")</script>')

        res = self.client.get(self.url)
        assert '<script>alert(' not in res.content
        assert '&lt;script&gt;alert(' in res.content
        # Now do the POST to delete.
        res = self.client.post(self.delete_url, {'version_id': version.pk},
                               follow=True)
        assert not Version.objects.filter(pk=version.pk).exists()
        # Check xss in success flash message.
        assert '<script>alert(' not in res.content
        assert '&lt;script&gt;alert(' in res.content

    def test_delete_only_version(self):
        eq_(self.app.versions.count(), 1)
        version = self.app.latest_version

        self.client.post(self.delete_url, {'version_id': version.pk})
        assert not Version.objects.filter(pk=version.pk).exists()
        eq_(ActivityLog.objects.filter(action=mkt.LOG.DELETE_VERSION.id)
                               .count(), 1)
        # Since this was the last version, the app status should be incomplete.
        eq_(self.get_app().status, mkt.STATUS_NULL)

    def test_delete_last_public_version(self):
        """
        Test that deleting the last PUBLIC version but there is an APPROVED
        version marks the app as APPROVED.
        Similar to the above test but ensures APPROVED versions don't get
        confused with PUBLIC versions.
        """
        eq_(self.app.versions.count(), 1)
        ver1 = self.app.latest_version
        ver1.all_files[0].update(status=mkt.STATUS_APPROVED)
        ver2 = version_factory(
            addon=self.app, version='2.0',
            file_kw=dict(status=mkt.STATUS_PUBLIC))

        self.client.post(self.delete_url, {'version_id': ver2.pk})

        self.app.reload()
        eq_(self.app.status, mkt.STATUS_APPROVED)
        eq_(self.app.latest_version, ver1)
        eq_(self.app.current_version, None)
        eq_(self.app.versions.count(), 1)
        eq_(Version.with_deleted.get(pk=ver2.pk).all_files[0].status,
            mkt.STATUS_DISABLED)

    def test_delete_version_app_public(self):
        """Test deletion of current_version when app is PUBLIC."""
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        ver1 = self.app.latest_version
        ver2 = version_factory(
            addon=self.app, version='2.0',
            file_kw=dict(status=mkt.STATUS_PUBLIC))
        eq_(self.app.latest_version, ver2)
        eq_(self.app.current_version, ver2)

        self.client.post(self.delete_url, {'version_id': ver2.pk})

        self.app.reload()
        eq_(self.app.status, mkt.STATUS_PUBLIC)
        eq_(self.app.latest_version, ver1)
        eq_(self.app.current_version, ver1)
        eq_(self.app.versions.count(), 1)
        eq_(Version.with_deleted.get(pk=ver2.pk).all_files[0].status,
            mkt.STATUS_DISABLED)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_delete_version_app_hidden(self, update_name_mock,
                                       update_manifest_mock, index_mock):
        """Test deletion of current_version when app is UNLISTED."""
        self.app.update(status=mkt.STATUS_UNLISTED)
        ver1 = self.app.latest_version
        ver2 = version_factory(
            addon=self.app, version='2.0',
            file_kw=dict(status=mkt.STATUS_PUBLIC))
        eq_(self.app.latest_version, ver2)
        eq_(self.app.current_version, ver2)

        update_manifest_mock.reset_mock()
        index_mock.reset_mock()

        self.client.post(self.delete_url, {'version_id': ver2.pk})

        self.app.reload()
        eq_(self.app.status, mkt.STATUS_UNLISTED)
        eq_(self.app.latest_version, ver1)
        eq_(self.app.current_version, ver1)
        eq_(self.app.versions.count(), 1)
        eq_(Version.with_deleted.get(pk=ver2.pk).all_files[0].status,
            mkt.STATUS_DISABLED)

        eq_(update_name_mock.call_count, 1)
        eq_(update_manifest_mock.delay.call_count, 1)
        eq_(index_mock.delay.call_count, 1)

    @mock.patch('mkt.webapps.tasks.index_webapps')
    @mock.patch('mkt.webapps.tasks.update_cached_manifests')
    @mock.patch('mkt.webapps.models.Webapp.update_name_from_package_manifest')
    def test_delete_version_app_private(self, update_name_mock,
                                        update_manifest_mock, index_mock):
        """Test deletion of current_version when app is APPROVED."""
        self.app.update(status=mkt.STATUS_APPROVED)
        ver1 = self.app.latest_version
        ver2 = version_factory(
            addon=self.app, version='2.0',
            file_kw=dict(status=mkt.STATUS_PUBLIC))
        eq_(self.app.latest_version, ver2)
        eq_(self.app.current_version, ver2)

        update_manifest_mock.reset_mock()
        index_mock.reset_mock()

        self.client.post(self.delete_url, {'version_id': ver2.pk})

        self.app.reload()
        eq_(self.app.status, mkt.STATUS_APPROVED)
        eq_(self.app.latest_version, ver1)
        eq_(self.app.current_version, ver1)
        eq_(self.app.versions.count(), 1)
        eq_(Version.with_deleted.get(pk=ver2.pk).all_files[0].status,
            mkt.STATUS_DISABLED)

        eq_(update_name_mock.call_count, 1)
        eq_(update_manifest_mock.delay.call_count, 1)
        eq_(index_mock.delay.call_count, 1)

    def test_delete_version_while_disabled(self):
        self.app.update(disabled_by_user=True)
        version = self.app.latest_version

        res = self.client.post(self.delete_url, {'version_id': version.pk})
        eq_(res.status_code, 302)

        eq_(self.get_app().status, mkt.STATUS_NULL)
        version = Version.with_deleted.get(pk=version.pk)
        assert version.deleted

    def test_anonymous_delete_redirects(self):
        self.client.logout()
        version = self.app.versions.latest()
        res = self.client.post(self.delete_url, dict(version_id=version.pk))
        self.assertLoginRedirects(res, self.delete_url)

    def test_non_author_no_delete_for_you(self):
        self.client.logout()
        self.login('regular@mozilla.com')
        version = self.app.versions.latest()
        res = self.client.post(self.delete_url, dict(version_id=version.pk))
        eq_(res.status_code, 403)

    @mock.patch.object(Version, 'delete')
    def test_roles_and_delete(self, mock_version):
        user = UserProfile.objects.get(email='regular@mozilla.com')
        addon_user = AddonUser.objects.create(user=user, addon=self.app)
        allowed = [mkt.AUTHOR_ROLE_OWNER, mkt.AUTHOR_ROLE_DEV]
        for role in [r[0] for r in mkt.AUTHOR_CHOICES]:
            self.client.logout()
            addon_user.role = role
            addon_user.save()
            self.login('regular@mozilla.com')
            version = self.app.versions.latest()
            res = self.client.post(self.delete_url,
                                   dict(version_id=version.pk))
            if role in allowed:
                self.assert3xx(res, self.url)
                assert mock_version.called, ('Unexpected: `Version.delete` '
                                             'should have been called.')
                mock_version.reset_mock()
            else:
                eq_(res.status_code, 403)

    def test_cannot_delete_blocked(self):
        v = self.app.versions.latest()
        f = v.all_files[0]
        f.update(status=mkt.STATUS_BLOCKED)
        res = self.client.post(self.delete_url, dict(version_id=v.pk))
        eq_(res.status_code, 403)

    def test_dev_cannot_blocklist(self):
        url = self.app.get_dev_url('blocklist')
        res = self.client.post(url)
        eq_(res.status_code, 403)

    @mock.patch('lib.crypto.packaged.os.unlink', new=mock.Mock)
    def test_admin_can_blocklist(self):
        blocklist_zip_path = os.path.join(settings.MEDIA_ROOT,
                                          'packaged-apps', 'blocklisted.zip')
        if storage_is_remote():
            copy_stored_file(blocklist_zip_path, blocklist_zip_path,
                             src_storage=local_storage,
                             dst_storage=private_storage)
        self.grant_permission(
            UserProfile.objects.get(email='regular@mozilla.com'),
            'Apps:Configure')
        self.login('regular@mozilla.com')
        v_count = self.app.versions.count()
        url = self.app.get_dev_url('blocklist')
        res = self.client.post(url)
        self.assert3xx(res, self.app.get_dev_url('versions'))
        app = self.app.reload()
        eq_(app.versions.count(), v_count + 1)
        eq_(app.status, mkt.STATUS_BLOCKED)
        eq_(app.versions.latest().files.latest().status, mkt.STATUS_BLOCKED)
