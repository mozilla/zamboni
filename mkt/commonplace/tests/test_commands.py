from django.core.management import call_command

import mock
from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.commonplace.models import DeployBuildId


class TestSetBuildId(mkt.site.tests.TestCase):

    mock_path = (
        'mkt.commonplace.management.commands.deploy_build_id.local_storage')

    @mock.patch(mock_path)
    def test_initial(self, storage_mock):
        storage_mock.open = mock.mock_open(read_data='0118999a')

        eq_(DeployBuildId.objects.count(), 0)
        call_command('deploy_build_id', 'fireplace')
        ok_(DeployBuildId.objects.get(repo='fireplace', build_id='0118999a'))

    @mock.patch(mock_path)
    def test_update(self, storage_mock):
        DeployBuildId.objects.create(repo='fireplace', build_id='12345')
        storage_mock.open = mock.mock_open(read_data='0118999')

        call_command('deploy_build_id', 'fireplace')
        eq_(DeployBuildId.objects.get(repo='fireplace').build_id, '0118999')

    @mock.patch(mock_path)
    def test_multiple_repo(self, storage_mock):
        DeployBuildId.objects.create(repo='transonic', build_id='12345')
        DeployBuildId.objects.create(repo='fireplace', build_id='67890')
        storage_mock.open = mock.mock_open(read_data='0118999')

        call_command('deploy_build_id', 'transonic')
        eq_(DeployBuildId.objects.get(repo='transonic').build_id, '0118999')
        eq_(DeployBuildId.objects.get(repo='fireplace').build_id, '67890')

    @mock.patch(mock_path)
    def test_multiple_repo_build_id_passed_as_argument(self, storage_mock):
        DeployBuildId.objects.create(repo='transonic', build_id='12345')
        DeployBuildId.objects.create(repo='fireplace', build_id='666')
        storage_mock.open = mock.mock_open(read_data='0118999')

        call_command('deploy_build_id', 'transonic', '4815162342')
        eq_(DeployBuildId.objects.get(repo='transonic').build_id, '4815162342')
        eq_(DeployBuildId.objects.get(repo='fireplace').build_id, '666')
        ok_(not storage_mock.open.called)
