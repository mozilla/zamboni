# -*- coding: utf-8 -*-
import os
from datetime import datetime

from django.conf import settings
from django.core.management import call_command

import mock
from nose.tools import eq_

import mkt
import mkt.site.tests
from mkt.api.models import Nonce
from mkt.developers.models import ActivityLog
from mkt.files.models import File, FileUpload
from mkt.search.utils import get_popularity, get_trending
from mkt.site.fixtures import fixture
from mkt.site.storage_utils import private_storage, public_storage
from mkt.users.models import UserProfile
from mkt.versions.models import Version
from mkt.webapps import cron
from mkt.webapps.cron import (_get_installs, _get_trending, clean_old_signed,
                              mkt_gc, update_app_installs, update_app_trending)
from mkt.webapps.models import Installs, Trending, Webapp


class TestLastUpdated(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def test_catchall(self):
        """Make sure the catch-all last_updated is stable and accurate."""
        # Nullify all datestatuschanged so the public add-ons hit the
        # catch-all.
        (File.objects.filter(status=mkt.STATUS_PUBLIC)
         .update(datestatuschanged=None))
        Webapp.objects.update(last_updated=None)

        cron.addon_last_updated()
        for addon in Webapp.objects.filter(status=mkt.STATUS_PUBLIC):
            eq_(addon.last_updated, addon.created)

        # Make sure it's stable.
        cron.addon_last_updated()
        for addon in Webapp.objects.filter(status=mkt.STATUS_PUBLIC):
            eq_(addon.last_updated, addon.created)


class TestHideDisabledFiles(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    msg = 'Moving disabled file: %s => %s'

    def setUp(self):
        self.addon = Webapp.objects.get(pk=337141)
        self.version = self.addon.latest_version
        self.f1 = self.version.all_files[0]

    @mock.patch('mkt.files.models.os')
    def test_leave_nondisabled_files(self, os_mock):
        stati = [(mkt.STATUS_PUBLIC, mkt.STATUS_PUBLIC)]
        for addon_status, file_status in stati:
            self.addon.update(status=addon_status)
            File.objects.update(status=file_status)
            cron.hide_disabled_files()
            assert not os_mock.path.exists.called, (addon_status, file_status)

    @mock.patch('mkt.files.models.File.mv')
    @mock.patch('mkt.files.models.public_storage')
    def test_move_user_disabled_addon(self, m_storage, mv_mock):
        # Use Webapp.objects.update so the signal handler isn't called.
        Webapp.objects.filter(id=self.addon.id).update(
            status=mkt.STATUS_PUBLIC, disabled_by_user=True)
        File.objects.update(status=mkt.STATUS_PUBLIC)
        cron.hide_disabled_files()

        # Check that f1 was moved.
        mv_mock.assert_called_with(self.f1.file_path,
                                   self.f1.guarded_file_path, self.msg,
                                   src_storage=m_storage,
                                   dest_storage=private_storage)
        # There's only 1 file.
        eq_(mv_mock.call_count, 1)

    @mock.patch('mkt.files.models.File.mv')
    @mock.patch('mkt.files.models.public_storage')
    def test_move_admin_disabled_addon(self, m_storage, mv_mock):
        Webapp.objects.filter(id=self.addon.id).update(
            status=mkt.STATUS_DISABLED)
        File.objects.update(status=mkt.STATUS_PUBLIC)
        cron.hide_disabled_files()
        # Check that f1 was moved.
        mv_mock.assert_called_with(self.f1.file_path,
                                   self.f1.guarded_file_path, self.msg,
                                   src_storage=m_storage,
                                   dest_storage=private_storage)
        # There's only 1 file.
        eq_(mv_mock.call_count, 1)

    @mock.patch('mkt.files.models.File.mv')
    @mock.patch('mkt.files.models.private_storage')
    def test_move_disabled_file(self, m_storage, mv_mock):
        Webapp.objects.filter(id=self.addon.id).update(
            status=mkt.STATUS_REJECTED)
        File.objects.filter(id=self.f1.id).update(status=mkt.STATUS_DISABLED)
        cron.hide_disabled_files()
        # f1 should have been moved.
        mv_mock.assert_called_with(self.f1.file_path,
                                   self.f1.guarded_file_path, self.msg,
                                   src_storage=public_storage,
                                   dest_storage=m_storage)
        eq_(mv_mock.call_count, 1)

    @mock.patch('mkt.files.models.File.mv')
    @mock.patch('mkt.files.models.public_storage')
    def test_ignore_deleted_versions(self, m_storage, mv_mock):
        # Apps only have 1 file and version delete only deletes one.
        self.version.delete()
        mv_mock.reset_mock()
        # Create a new version/file just like the one we deleted.
        version = Version.objects.create(addon=self.addon)
        File.objects.create(version=version, filename='f2')
        cron.hide_disabled_files()
        # Mock shouldn't have been called.
        assert not mv_mock.called, mv_mock.call_args


class TestCleanup(mkt.site.tests.TestCase):

    def setUp(self):
        self.file = os.path.join(settings.SIGNED_APPS_REVIEWER_PATH,
                                 '1', 'x.z')

    def test_not_cleaned(self):
        with private_storage.open(self.file, 'w') as f:
            f.write('.')
        clean_old_signed()
        assert private_storage.exists(self.file)

    def test_cleaned(self):
        with private_storage.open(self.file, 'w') as f:
            f.write('.')
        clean_old_signed(-60)
        assert not private_storage.exists(self.file)


@mock.patch('lib.crypto.packaged.sign_app')
@mock.patch('mkt.webapps.models.Webapp.get_cached_manifest', mock.Mock)
class TestSignApps(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(id=337141)
        self.app.update(is_packaged=True)
        self.app2 = mkt.site.tests.app_factory(
            name=u'Mozillaball ょ', app_slug='test',
            is_packaged=True, version_kw={'version': '1.0',
                                          'created': None})
        self.app3 = mkt.site.tests.app_factory(
            name='Test app 3', app_slug='test3', status=mkt.STATUS_REJECTED,
            is_packaged=True, version_kw={'version': '1.0',
                                          'created': None})

    def test_by_webapp(self, sign_mock):
        v1 = self.app.current_version
        call_command('sign_apps', webapps=str(v1.pk))
        file1 = v1.all_files[0]
        assert sign_mock.called_with(((file1.file_path,
                                       file1.signed_file_path),))

    def test_all(self, sign_mock):
        v1 = self.app.current_version
        v2 = self.app2.current_version
        file1 = v1.all_files[0]
        file2 = v2.all_files[0]
        with public_storage.open(file1.file_path, 'w') as f:
            f.write('.')
        with public_storage.open(file2.file_path, 'w') as f:
            f.write('.')
        call_command('sign_apps')
        eq_(len(sign_mock.mock_calls), 2)
        eq_(os.path.join('/', sign_mock.mock_calls[0][1][0].name),
            file1.file_path)
        eq_(sign_mock.mock_calls[0][1][1], file1.signed_file_path)
        eq_(os.path.join('/', sign_mock.mock_calls[1][1][0].name),
            file2.file_path)
        eq_(sign_mock.mock_calls[1][1][1], file2.signed_file_path)


@mock.patch('mkt.webapps.cron.private_storage')
@mock.patch('mkt.webapps.cron.public_storage')
class TestGarbage(mkt.site.tests.TestCase):

    def setUp(self):
        self.user = UserProfile.objects.create(
            email='gc_test@example.com', name='gc_test')
        mkt.log(mkt.LOG.CUSTOM_TEXT, 'testing', user=self.user,
                created=datetime(2001, 1, 1))

    def test_garbage_collection(self, public_mock, private_mock):
        eq_(ActivityLog.objects.all().count(), 1)
        mkt_gc()
        eq_(ActivityLog.objects.all().count(), 0)

    def test_nonce(self, public_mock, private_mock):
        nonce = Nonce.objects.create(nonce='a', timestamp=1, client_key='b')
        nonce.update(created=self.days_ago(2))
        eq_(Nonce.objects.count(), 1)
        mkt_gc()
        eq_(Nonce.objects.count(), 0)

    def test_dump_delete(self, public_mock, private_mock):
        public_mock.listdir.return_value = (['dirlol'], ['lol'])
        public_mock.modified_time.return_value = self.days_ago(1000)

        mkt_gc()
        assert public_mock.delete.called
        assert not private_mock.delete.called
        assert public_mock.delete.call_args_list[0][0][0].endswith('lol')

    def test_dump_delete_private(self, public_mock, private_mock):
        private_mock.listdir.return_value = (['dirlol'], ['lol'])
        private_mock.modified_time.return_value = self.days_ago(1000)

        mkt_gc()
        assert private_mock.delete.called
        assert not public_mock.delete.called
        assert private_mock.delete.call_args_list[0][0][0].endswith('lol')

    def test_new_no_delete(self, public_mock, private_mock):
        public_mock.listdir.return_value = (['dirlol'], ['lol'])
        public_mock.modified_time.return_value = self.days_ago(1)

        mkt_gc()
        assert not public_mock.delete.called
        assert not private_mock.delete.called

    def test_old_and_new(self, public_mock, private_mock):
        fu_new = FileUpload.objects.create(path='/tmp/bar', name='bar')
        fu_new.created = self.days_ago(5)
        fu_old = FileUpload.objects.create(path='/tmp/foo', name='foo')
        fu_old.update(created=self.days_ago(91))

        mkt_gc()

        eq_(FileUpload.objects.count(), 1)
        assert private_mock.delete.called
        assert not public_mock.delete.called
        eq_(private_mock.delete.call_args[0][0], fu_old.path)

    def test_old_no_path(self, public_mock, private_mock):
        fu_old = FileUpload.objects.create(path='', name='foo')
        fu_old.update(created=self.days_ago(91))

        mkt_gc()

        eq_(FileUpload.objects.count(), 0)
        assert not private_mock.delete.called
        assert not public_mock.delete.called


class TestUpdateInstalls(mkt.site.tests.TestCase):

    def setUp(self):
        self.app = Webapp.objects.create(status=mkt.STATUS_PUBLIC)

    @mock.patch('mkt.webapps.cron._get_installs')
    def test_installs_saved(self, _mock):
        _mock.return_value = {'all': 12.0}
        update_app_installs()

        eq_(get_popularity(self.app), 12.0)
        for region in mkt.regions.REGIONS_DICT.values():
            if region.adolescent:
                eq_(get_popularity(self.app, region=region), 12.0)
            else:
                eq_(get_popularity(self.app, region=region), 0.0)

        # Test running again updates the values as we'd expect.
        _mock.return_value = {'all': 2.0}
        update_app_installs()
        eq_(get_popularity(self.app), 2.0)
        for region in mkt.regions.REGIONS_DICT.values():
            if region.adolescent:
                eq_(get_popularity(self.app, region=region), 2.0)
            else:
                eq_(get_popularity(self.app, region=region), 0.0)

    @mock.patch('mkt.webapps.cron._get_installs')
    def test_installs_deleted(self, _mock):
        self.app.trending.get_or_create(region=0, value=12.0)

        _mock.return_value = {'all': 0.0}
        update_app_installs()

        with self.assertRaises(Installs.DoesNotExist):
            self.app.popularity.get(region=0)

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending(self, _mock):
        client = mock.Mock()
        client.raw.return_value = {
            'aggregations': {
                'popular': {'total_installs': {'value': 123}},
                'region': {
                    'buckets': [
                        {
                            'key': 'br',
                            'popular': {'total_installs': {'value': 12}}
                        }
                    ]
                }
            }
        }
        _mock.return_value = client

        eq_(_get_installs(self.app.id)['all'], 123.0)
        eq_(_get_installs(self.app.id)['br'], 12.0)

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_installs_error(self, _mock):
        client = mock.Mock()
        client.raw.side_effect = ValueError
        _mock.return_value = client

        eq_(_get_installs(self.app.id), {})


class TestUpdateTrending(mkt.site.tests.TestCase):

    def setUp(self):
        self.app = Webapp.objects.create(status=mkt.STATUS_PUBLIC)

    @mock.patch('mkt.webapps.cron._get_trending')
    def test_trending_saved(self, _mock):
        _mock.return_value = {'all': 12.0}
        update_app_trending()

        eq_(get_trending(self.app), 12.0)
        for region in mkt.regions.REGIONS_DICT.values():
            if region.adolescent:
                eq_(get_trending(self.app, region=region), 12.0)
            else:
                eq_(get_trending(self.app, region=region), 0.0)

        # Test running again updates the values as we'd expect.
        _mock.return_value = {'all': 2.0}
        update_app_trending()
        eq_(get_trending(self.app), 2.0)
        for region in mkt.regions.REGIONS_DICT.values():
            if region.adolescent:
                eq_(get_trending(self.app, region=region), 2.0)
            else:
                eq_(get_trending(self.app, region=region), 0.0)

    @mock.patch('mkt.webapps.cron._get_trending')
    def test_trending_deleted(self, _mock):
        self.app.trending.get_or_create(region=0, value=12.0)

        _mock.return_value = {'all': 0.0}
        update_app_trending()

        with self.assertRaises(Trending.DoesNotExist):
            self.app.trending.get(region=0)

    def _return_value(self, week1, week3):
        return {
            'aggregations': {
                'week1': {'total_installs': {'value': week1}},
                'week3': {'total_installs': {'value': week3}},
            }
        }

    def _return_value_with_regions(self, week1, week3, rweek1, rweek3):
        return {
            'aggregations': {
                'week1': {'total_installs': {'value': week1}},
                'week3': {'total_installs': {'value': week3}},
                'region': {
                    'buckets': [
                        {
                            'key': 'br',
                            'week1': {'total_installs': {'value': rweek1}},
                            'week3': {'total_installs': {'value': rweek3}},
                        },
                    ]
                }
            }
        }

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value(255, 255)
        _mock.return_value = client

        # 1st week count: 255
        # Prior 3 weeks get averaged: (255) / 3 = 85
        # (255 - 85) / 85 = 2.0
        eq_(_get_trending(self.app.id), {'all': 2.0})

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_threshold(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value(99, 2)
        _mock.return_value = client

        # 1st week count: 99
        # 99 is less than 100 so we return {} as not trending.
        eq_(_get_trending(self.app.id), {})

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_negative(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value(100, 1000)
        _mock.return_value = client

        # 1st week count: 100
        # Prior 3 week count: 1000/3 = 333.3
        # (100 - 333.3) / 333.3 = -0.7 which gets set to 0.0.
        eq_(_get_trending(self.app.id), {'all': 0.0})

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_regional(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value_with_regions(102, 102,
                                                                  255, 102)
        _mock.return_value = client

        # We set global counts to anything over 100. See above tests. I chose
        # 102 to divide equally by 3 w/o a crazy remainder.
        #
        # 1st week regional count: 255
        # Prior 3 week regional count: 102/3 = 34
        # (255 - 34) / 34 = 6.5
        eq_(_get_trending(self.app.id)['br'], 6.5)
        # Make sure global trending is still correct.
        eq_(_get_trending(self.app.id)['all'], 2.0)

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_regional_threshold(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value_with_regions(102, 102,
                                                                  99, 99)
        _mock.return_value = client

        # 1st week regional count: 99
        # Prior 3 week regional count: 99/3 = 33
        # (99 - 33) / 33 = 2.0 but week1 isn't > 100 so we set to zero.
        eq_(_get_trending(self.app.id)['br'], 0.0)
        # Make sure global trending is still correct.
        eq_(_get_trending(self.app.id)['all'], 2.0)

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_regional_negative(self, _mock):
        client = mock.Mock()
        client.raw.return_value = self._return_value_with_regions(102, 102,
                                                                  100, 1000)
        _mock.return_value = client

        # 1st week regional count: 99
        # Prior 3 week regional count: 99/3 = 33
        # (99 - 33) / 33 = 2.0 but week1 isn't > 100 so we set to zero.
        eq_(_get_trending(self.app.id)['br'], 0.0)
        # Make sure global trending is still correct.
        eq_(_get_trending(self.app.id)['all'], 2.0)

    @mock.patch('mkt.webapps.cron.get_monolith_client')
    def test_get_trending_error(self, _mock):
        client = mock.Mock()
        client.raw.side_effect = ValueError
        _mock.return_value = client

        eq_(_get_trending(self.app.id), {})
