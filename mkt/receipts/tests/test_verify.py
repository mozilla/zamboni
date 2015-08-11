# -*- coding: utf-8 -*-
import calendar
import time
import uuid
from urllib import urlencode

from django.db import connection
from django.conf import settings
from django.test.client import RequestFactory

import jwt
import M2Crypto
import mock
from browserid.errors import ExpiredSignatureError
from nose.tools import eq_, ok_
from services import utils, verify

import mkt
import mkt.site.tests
from mkt.inapp.models import InAppProduct
from mkt.prices.models import WebappPurchase, Price
from mkt.purchase.models import Contribution
from mkt.receipts.utils import create_receipt, create_receipt_data
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile
from mkt.webapps.models import Webapp


def get_response(data, status):
    response = mock.Mock()
    response.read.return_value = data
    response.getcode.return_value = status
    return response


class ReceiptTest(mkt.site.tests.TestCase):
    fixtures = fixture('prices', 'webapp_337141', 'user_999')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.inapp = InAppProduct.objects.create(logo_url='image.png',
                                                 name='Kiwii',
                                                 price=Price.objects.get(pk=1),
                                                 webapp=self.app)
        self.inapp.save()  # generates a GUID
        self.user = UserProfile.objects.get(pk=999)

    def sample_app_receipt(self):
        return create_receipt_data(self.app, self.user, 'some-uuid')

    def sample_inapp_receipt(self, contribution):
        return create_receipt_data(contribution.webapp,
                                   contribution.user,
                                   'some-uuid',
                                   flavour='inapp',
                                   contrib=contribution)


# There are two "different" settings files that need to be patched,
# even though they are the same file.
@mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_KEY',
                   mkt.site.tests.MktPaths.sample_key())
@mock.patch.object(settings, 'SITE_URL', 'http://foo.com/')
@mock.patch.object(settings, 'WEBAPPS_RECEIPT_URL', '/verifyme/')
class TestVerify(ReceiptTest):

    def verify_signed_receipt(self, signed_receipt, check_purchase=True):
        # Ensure that the verify code is using the test database cursor.
        verifier = verify.Verify(
            signed_receipt,
            RequestFactory().get('/verifyme/').META
        )
        verifier.cursor = connection.cursor()

        if check_purchase:
            return verifier.check_full()
        else:
            return verifier.check_without_purchase()

    @mock.patch.object(verify, 'decode_receipt')
    def verify_receipt_data(self, receipt_data, decode_receipt,
                            check_purchase=True):
        # Override the decoder to return the unsigned receipt data
        decode_receipt.return_value = receipt_data
        # Pass in an empty signed receipt because the
        # decoder will spit out the actual receipt
        return self.verify_signed_receipt('', check_purchase=check_purchase)

    def make_purchase(self):
        return WebappPurchase.objects.create(webapp=self.app, user=self.user,
                                             uuid='some-uuid')

    def make_contribution(self, type=mkt.CONTRIB_PURCHASE):
        contribution = Contribution.objects.create(webapp=self.app,
                                                   user=self.user,
                                                   type=type)
        # This was created by the contribution, but we need to tweak
        # the uuid to ensure its correct.
        WebappPurchase.objects.get().update(uuid='some-uuid')
        return contribution

    def make_inapp_contribution(self, type=mkt.CONTRIB_PURCHASE):
        return Contribution.objects.create(
            webapp=self.app,
            inapp_product=self.inapp,
            type=type,
            user=self.user,
        )

    @mock.patch.object(utils.settings, 'SIGNING_SERVER_ACTIVE', True)
    def test_invalid_receipt(self):
        eq_(self.verify_signed_receipt('blah')['status'], 'invalid')

    def test_invalid_signature(self):
        eq_(self.verify_signed_receipt('blah.blah.blah')['status'], 'invalid')

    @mock.patch('services.verify.receipt_cef.log')
    def test_no_user(self, log):
        receipt_data = self.sample_app_receipt()
        del receipt_data['user']
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_DIRECTED_IDENTIFIER')
        ok_(log.called)

    def test_no_app(self):
        receipt_data = self.sample_app_receipt()
        del receipt_data['product']
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'WRONG_STOREDATA')

    def test_user_type_incorrect(self):
        receipt_data = self.sample_app_receipt()
        receipt_data['user']['type'] = 'nope'
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_DIRECTED_IDENTIFIER')

    def test_type(self):
        receipt_data = self.sample_app_receipt()
        receipt_data['typ'] = 'anything'
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'WRONG_TYPE')

    def test_user_incorrect(self):
        receipt_data = self.sample_app_receipt()
        receipt_data['user']['value'] = 'ugh'
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_PURCHASE')

    def test_user_deleted(self):
        self.user.delete()
        res = self.verify_receipt_data(self.sample_app_receipt())
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_PURCHASE')

    @mock.patch('services.verify.sign')
    @mock.patch('services.verify.receipt_cef.log')
    def test_expired(self, log, sign):
        sign.return_value = ''
        receipt_data = self.sample_app_receipt()
        receipt_data['exp'] = calendar.timegm(time.gmtime()) - 1000
        self.make_purchase()
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'expired')
        ok_(log.called)

    @mock.patch('services.verify.sign')
    def test_garbage_expired(self, sign):
        sign.return_value = ''
        receipt_data = self.sample_app_receipt()
        receipt_data['exp'] = 'a'
        self.make_purchase()
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'expired')

    @mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_EXPIRED_SEND', True)
    @mock.patch('services.verify.sign')
    def test_expired_has_receipt(self, sign):
        sign.return_value = ''
        receipt_data = self.sample_app_receipt()
        receipt_data['exp'] = calendar.timegm(time.gmtime()) - 1000
        self.make_purchase()
        res = self.verify_receipt_data(receipt_data)
        assert 'receipt' in res

    @mock.patch.object(utils.settings, 'SIGNING_SERVER_ACTIVE', True)
    @mock.patch('services.verify.receipts.certs.ReceiptVerifier.verify')
    def test_expired_cert(self, mthd):
        mthd.side_effect = ExpiredSignatureError
        assert 'typ' in verify.decode_receipt(
            'jwt_public_key~' + create_receipt(
                self.app, self.user, str(uuid.uuid4())))

    @mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_EXPIRED_SEND', True)
    @mock.patch('services.verify.sign')
    def test_new_expiry(self, sign):
        receipt_data = self.sample_app_receipt()
        receipt_data['exp'] = old = calendar.timegm(time.gmtime()) - 10000
        self.make_purchase()
        sign.return_value = ''
        self.verify_receipt_data(receipt_data)
        assert sign.call_args[0][0]['exp'] > old

    def test_expired_not_signed(self):
        receipt_data = self.sample_app_receipt()
        receipt_data['exp'] = calendar.timegm(time.gmtime()) - 10000
        self.make_purchase()
        res = self.verify_receipt_data(receipt_data)
        eq_(res['status'], 'expired')

    def test_premium_app_not_purchased(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        res = self.verify_receipt_data(self.sample_app_receipt())
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_PURCHASE')

    def test_premium_dont_check(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        res = self.verify_receipt_data(
            self.sample_app_receipt(),
            check_purchase=False
        )
        # Because the receipt is the wrong type for skipping purchase.
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'WRONG_TYPE')

    @mock.patch.object(utils.settings, 'DOMAIN', 'foo.com')
    def test_premium_dont_check_properly(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        receipt_data = self.sample_app_receipt()
        receipt_data['typ'] = 'developer-receipt'
        res = self.verify_receipt_data(receipt_data, check_purchase=False)
        eq_(res['status'], 'ok', res)

    def test_premium_app_purchased(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        self.make_purchase()
        res = self.verify_receipt_data(self.sample_app_receipt())
        eq_(res['status'], 'ok', res)

    def test_inapp_purchased(self):
        contribution = self.make_inapp_contribution()
        res = self.verify_receipt_data(self.sample_inapp_receipt(contribution))
        eq_(res['status'], 'ok', res)

    def test_premium_app_contribution(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        # There's no purchase, but the last entry we have is a sale.
        self.make_contribution()
        res = self.verify_receipt_data(self.sample_app_receipt())
        eq_(res['status'], 'ok', res)

    @mock.patch('services.verify.receipt_cef.log')
    def test_premium_app_refund(self, log):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        purchase = self.make_purchase()
        for type in [mkt.CONTRIB_REFUND, mkt.CONTRIB_CHARGEBACK]:
            purchase.update(type=type)
            res = self.verify_receipt_data(self.sample_app_receipt())
            eq_(res['status'], 'refunded')
        eq_(log.call_count, 2)

    @mock.patch('services.verify.receipt_cef.log')
    def test_inapp_refund(self, log):
        for type in [mkt.CONTRIB_REFUND, mkt.CONTRIB_CHARGEBACK]:
            contribution = self.make_inapp_contribution(type=type)
            res = self.verify_receipt_data(
                self.sample_inapp_receipt(contribution))
            eq_(res['status'], 'refunded')
        eq_(log.call_count, 2)

    def test_premium_no_charge(self):
        self.app.update(premium_type=mkt.WEBAPP_PREMIUM)
        purchase = self.make_purchase()
        purchase.update(type=mkt.CONTRIB_NO_CHARGE)
        res = self.verify_receipt_data(self.sample_app_receipt())
        eq_(res['status'], 'ok', res)

    def test_inapp_no_charge(self):
        contribution = self.make_inapp_contribution(type=mkt.CONTRIB_NO_CHARGE)
        res = self.verify_receipt_data(self.sample_inapp_receipt(contribution))
        eq_(res['status'], 'ok', res)

    def test_other_premiums(self):
        self.make_purchase()
        for k in (mkt.WEBAPP_PREMIUM, mkt.WEBAPP_PREMIUM_INAPP):
            self.app.update(premium_type=k)
            res = self.verify_receipt_data(self.sample_app_receipt())
            eq_(res['status'], 'ok', res)

    def test_product_wrong_store_data(self):
        self.make_purchase()
        data = self.sample_app_receipt()
        data['product'] = {'url': 'http://f.com',
                           'storedata': urlencode({'id': 123})}
        eq_(self.verify_receipt_data(data)['status'], 'invalid')

    def test_product_ok_store_data(self):
        self.make_purchase()
        data = self.sample_app_receipt()
        data['product'] = {'url': 'http://f.com',
                           'storedata': urlencode({'id': 337141})}
        eq_(self.verify_receipt_data(data)['status'], 'ok')

    def test_product_barf_store_data_for_app(self):
        self.make_purchase()
        for storedata in (urlencode({'id': 'NaN'}), 'NaN'):
            data = self.sample_app_receipt()
            data['product'] = {'url': 'http://f.com', 'storedata': storedata}
            res = self.verify_receipt_data(data)
            eq_(res['status'], 'invalid')
            eq_(res['reason'], 'WRONG_STOREDATA')

    def test_product_barf_store_data_for_inapp(self):
        contribution = self.make_inapp_contribution()
        for storedata in (urlencode({'id': 'NaN'}),
                          urlencode({'id': '123', 'contrib': 'NaN'}),
                          'NaN'):
            data = self.sample_inapp_receipt(contribution)
            data['product'] = {'url': 'http://f.com', 'storedata': storedata}
            res = self.verify_receipt_data(data)
            eq_(res['status'], 'invalid')
            eq_(res['reason'], 'WRONG_STOREDATA')

    def test_inapp_product_matches_contribution(self):
        contribution = self.make_inapp_contribution()
        receipt = self.sample_inapp_receipt(contribution)
        receipt['product']['storedata'] = urlencode({
            'contrib': contribution.id,
            # Set the inapp_id to the wrong guid
            'inapp_id': 'incorrect-guid',
        })

        res = self.verify_receipt_data(receipt)
        eq_(res['status'], 'invalid')
        eq_(res['reason'], 'NO_PURCHASE')

    def test_crack_receipt(self):
        # Check that we can decode our receipt and get a dictionary back.
        self.app.update(manifest_url='http://a.com')
        purchase = self.make_purchase()
        receipt = create_receipt(purchase.webapp, purchase.user, purchase.uuid)
        result = verify.decode_receipt(receipt)
        eq_(result['typ'], u'purchase-receipt')

    @mock.patch('services.verify.settings')
    @mock.patch('services.verify.receipts.certs.ReceiptVerifier')
    def test_crack_receipt_new_called(self, trunion_verify, settings):
        # Check that we can decode our receipt and get a dictionary back.
        self.app.update(manifest_url='http://a.com')
        verify.decode_receipt(
            'jwt_public_key~' + create_receipt(
                self.app, self.user, str(uuid.uuid4())))
        assert trunion_verify.called

    def test_crack_borked_receipt(self):
        self.app.update(manifest_url='http://a.com')
        purchase = self.make_purchase()
        receipt = create_receipt(purchase.webapp, purchase.user, purchase.uuid)
        self.assertRaises(M2Crypto.RSA.RSAError, verify.decode_receipt,
                          receipt + 'x')

    @mock.patch.object(verify, 'decode_receipt')
    def get_headers(self, decode_receipt):
        decode_receipt.return_value = ''
        return verify.get_headers(verify.Verify('', mock.Mock()))

    def test_cross_domain(self):
        hdrs = dict(self.get_headers())
        eq_(hdrs['Access-Control-Allow-Origin'], '*')
        eq_(hdrs['Access-Control-Allow-Methods'], 'POST')
        eq_(hdrs['Access-Control-Allow-Headers'],
            'content-type, x-fxpay-version')

    def test_no_cache(self):
        hdrs = self.get_headers()
        assert ('Cache-Control', 'no-cache') in hdrs, 'No cache header needed'


class TestBase(mkt.site.tests.TestCase):

    def create(self, data, request=None):
        stuff = {'user': {'type': 'directed-identifier'}}
        stuff.update(data)
        key = jwt.rsa_load(settings.WEBAPPS_RECEIPT_KEY)
        receipt = jwt.encode(stuff, key, u'RS512')
        v = verify.Verify(receipt, request)
        v.decoded = v.decode()
        return v


class TestType(TestBase):

    @mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_KEY',
                       mkt.site.tests.MktPaths.sample_key())
    def test_no_type(self):
        self.create({'typ': 'test-receipt'}).check_type('test-receipt')

    def test_wrong_type(self):
        with self.assertRaises(verify.InvalidReceipt):
            self.create({}).check_type('test-receipt')

    def test_test_type(self):
        sample = {'typ': 'test-receipt'}
        with self.assertRaises(verify.InvalidReceipt):
            self.create(sample).check_type('blargh')


@mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_KEY',
                   mkt.site.tests.MktPaths.sample_key())
class TestURL(TestBase):

    def setUp(self):
        self.req = RequestFactory().post('/foo').META

    def test_wrong_domain(self):
        sample = {'verify': 'https://foo.com'}
        with self.assertRaises(verify.InvalidReceipt) as err:
            self.create(sample, request=self.req).check_url('f.com')
        eq_(str(err.exception), 'WRONG_DOMAIN')

    def test_wrong_path(self):
        sample = {'verify': 'https://f.com/bar'}
        with self.assertRaises(verify.InvalidReceipt) as err:
            self.create(sample, request=self.req).check_url('f.com')
        eq_(str(err.exception), 'WRONG_PATH')

    @mock.patch.object(utils.settings, 'WEBAPPS_RECEIPT_KEY',
                       mkt.site.tests.MktPaths.sample_key())
    def test_good(self):
        sample = {'verify': 'https://f.com/foo'}
        self.create(sample, request=self.req).check_url('f.com')


class TestServices(mkt.site.tests.TestCase):

    def test_wrong_settings(self):
        with self.settings(SIGNING_SERVER_ACTIVE=''):
            eq_(verify.status_check({})[0], 500)

    def test_options_request_for_cors(self):
        data = {}
        req = RequestFactory().options('/verify')

        def start_response(status, wsgi_headers):
            data['status'] = status
            data['headers'] = dict(wsgi_headers)

        verify.application(req.META, start_response)

        eq_(data['status'], '204 OK')
        eq_(data['headers']['Access-Control-Allow-Headers'],
            'content-type, x-fxpay-version')
        eq_(data['headers']['Content-Length'], '0')
