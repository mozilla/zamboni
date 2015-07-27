import time

from django.conf import settings
from django.test.utils import override_settings

from mock import Mock, patch
from nose.tools import eq_
import requests

import mkt.site.tests
from mkt.site import monitors


@patch.object(settings, 'SIGNED_APPS_SERVER_ACTIVE', True)
@patch.object(settings, 'SIGNING_SERVER', 'http://foo/')
@patch.object(settings, 'SIGNED_APPS_SERVER', 'http://baz/')
class TestMonitor(mkt.site.tests.TestCase):
    # TODO: Would be nice to test what happens when monitors.* methods fail.
    @patch('socket.socket')
    def test_memcache(self, mock_socket):
        mocked_caches = {
            'default': {
                'BACKEND': 'django.core.cache.backends.memcached'
                           '.MemcachedCache',
                'LOCATION': '127.0.0.1:6666'
            }
        }
        cache_info = mocked_caches['default']['LOCATION'].split(':')
        mock_socket_instance = Mock()
        mock_socket.return_value = mock_socket_instance
        with override_settings(CACHES=mocked_caches):
            status, memcache_results = monitors.memcache()
            eq_(status, '')

            # Expect socket.connect() to be called once, with the cache info.
            connect_call_args = mock_socket_instance.connect.call_args_list
            eq_(len(connect_call_args), 1)
            mock_socket_instance.connect.assert_called_with(
                (cache_info[0], int(cache_info[1])))

            # Expect memcached_results to contain cache info and then a boolean
            # indicating everything is OK.
            eq_(len(memcache_results), 1)
            eq_(list(memcache_results[0][0:2]), cache_info)
            eq_(memcache_results[0][2], True)

    @override_settings(SPIDERMONKEY='/bin/true')
    def test_libraries(self):
        status, libraries_result = monitors.libraries()
        eq_(status, '')
        eq_(libraries_result, [('PIL+JPEG', True, 'Got it!'),
                               ('M2Crypto', True, 'Got it!'),
                               ('Spidermonkey is ready!', True, None)])

    def test_elastic(self):
        status, elastic_result = monitors.elastic()
        eq_(status, '')

    def test_path(self):
        status, path_result = monitors.path()
        eq_(status, '')

    def test_settings_check(self):
        status, settings_check_result = monitors.settings_check()
        eq_(status, '')

    def _make_receipt(self):
        now = time.time()
        return [
            {'exp': now + (3600 * 36), 'iss': 'http://foo/cert.jwk'}, '']

    @patch('mkt.site.monitors.receipt')
    def test_sign_fails(self, receipt):
        from lib.crypto.receipt import SigningError
        receipt.sign.side_effect = SigningError
        eq_(monitors.receipt_signer()[0][:16], 'Error on signing')

    @patch('mkt.site.monitors.receipt')
    def test_crack_fails(self, receipt):
        receipt.crack.side_effect = ValueError
        eq_(monitors.receipt_signer()[0][:25], 'Error on cracking receipt')

    @patch('mkt.site.monitors.receipt')
    def test_expire(self, receipt):
        now = time.time()
        receipt.crack.return_value = [{'exp': now + (3600 * 12)}, '']
        eq_(monitors.receipt_signer()[0][:21], 'Cert will expire soon')

    @patch('requests.get')
    @patch('mkt.site.monitors.receipt')
    def test_good(self, receipt, cert_response):
        receipt.crack.return_value = self._make_receipt()
        cert_response.return_value.ok = True
        cert_response.return_value.json = lambda: {'jwk': []}
        eq_(monitors.receipt_signer()[0], '')

    @patch('requests.get')
    @patch('mkt.site.monitors.receipt')
    def test_public_cert_connection_error(self, receipt, cert_response):
        receipt.crack.return_value = self._make_receipt()
        cert_response.side_effect = Exception
        eq_(monitors.receipt_signer()[0][:29], 'Error on checking public cert')

    @patch('requests.get')
    @patch('mkt.site.monitors.receipt')
    def test_public_cert_not_found(self, receipt, cert_response):
        receipt.crack.return_value = self._make_receipt()
        cert_response.return_value.ok = False
        cert_response.return_value.reason = 'Not Found'
        eq_(monitors.receipt_signer()[0][:29], 'Error on checking public cert')

    @patch('requests.get')
    @patch('mkt.site.monitors.receipt')
    def test_public_cert_no_json(self, receipt, cert_response):
        receipt.crack.return_value = self._make_receipt()
        cert_response.return_value.ok = True
        cert_response.return_value.json = lambda: None
        eq_(monitors.receipt_signer()[0][:29], 'Error on checking public cert')

    @patch('requests.get')
    @patch('mkt.site.monitors.receipt')
    def test_public_cert_invalid_jwk(self, receipt, cert_response):
        receipt.crack.return_value = self._make_receipt()
        cert_response.return_value.ok = True
        cert_response.return_value.json = lambda: {'foo': 1}
        eq_(monitors.receipt_signer()[0][:29], 'Error on checking public cert')

    @patch('requests.post')
    def test_app_sign_good(self, sign_response):
        sign_response().status_code = 200
        sign_response().content = '{"zigbert.rsa": "Vm0wd2QyUXlVWGxW"}'
        eq_(monitors.package_signer()[0], '')

    @patch('mkt.site.monitors.os.unlink', new=Mock)
    @patch('requests.post')
    def test_app_sign_fail(self, sign_response):
        sign_response().side_effect = requests.exceptions.HTTPError
        assert monitors.package_signer()[0].startswith('Error on package sign')
