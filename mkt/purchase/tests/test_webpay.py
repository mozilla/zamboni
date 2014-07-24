import calendar
import json
import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

import fudge
import jwt
import mock
from mock import ANY
from mozpay.exc import RequestExpired
from nose.tools import eq_, raises

import amo
from mkt.api.exceptions import AlreadyPurchased
from mkt.prices.models import AddonPurchase
from mkt.purchase.models import Contribution
from mkt.users.models import UserProfile
from utils import PurchaseTest


class TestWebAppPurchase(PurchaseTest):

    def setUp(self):
        super(TestWebAppPurchase, self).setUp()
        self.create_flag(name='solitude-payments')
        self.prepare_pay = reverse('webpay.prepare_pay',
                                   kwargs={'app_slug': self.addon.app_slug})

    def _req(self, method, url):
        req = getattr(self.client, method)
        resp = req(url)
        eq_(resp.status_code, 200)
        eq_(resp['content-type'], 'application/json')
        return json.loads(resp.content)

    def get(self, url, **kw):
        return self._req('get', url, **kw)

    def post(self, url, **kw):
        return self._req('post', url, **kw)

    def test_pay_status(self):
        uuid = '<returned from prepare-pay>'
        contribution = Contribution.objects.create(addon_id=self.addon.id,
                                                   amount=self.price.price,
                                                   uuid=uuid,
                                                   type=amo.CONTRIB_PENDING,
                                                   user=self.user)

        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, uuid]))

        eq_(data['status'], 'incomplete')

        contribution.update(type=amo.CONTRIB_PURCHASE)

        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, uuid]))

        eq_(data['status'], 'complete')

    def test_status_for_purchases_only(self):
        uuid = '<returned from prepare-pay>'
        Contribution.objects.create(addon_id=self.addon.id,
                                    amount=self.price.price,
                                    uuid=uuid,
                                    type=amo.CONTRIB_PURCHASE,
                                    user=self.user)
        self.client.logout()
        assert self.client.login(username='admin@mozilla.com',
                                 password='password')
        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, uuid]))
        eq_(data['status'], 'incomplete')

    def test_pay_status_for_unknown_contrib(self):
        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, '<garbage>']))
        eq_(data['status'], 'incomplete')

    def test_strip_html(self):
        self.addon.description = 'Some <a href="http://soso.com">site</a>'
        self.addon.save()
        data = self.post(self.prepare_pay)
        data = jwt.decode(data['webpayJWT'].encode('ascii'), verify=False)
        req = data['request']
        eq_(req['description'], 'Some site')

    def test_status_for_already_purchased(self):
        AddonPurchase.objects.create(addon=self.addon,
                                     user=self.user,
                                     type=amo.CONTRIB_PURCHASE)

        with self.assertRaises(AlreadyPurchased):
            self.client.post(self.prepare_pay)

    def test_require_login(self):
        self.client.logout()
        resp = self.client.post(self.prepare_pay)
        self.assertLoginRequired(resp)


@mock.patch.object(settings, 'SOLITUDE_HOSTS', ['host'])
@mock.patch('mkt.purchase.webpay.tasks')
class TestPostback(PurchaseTest):

    def setUp(self):
        super(TestPostback, self).setUp()
        self.client.logout()
        self.contrib = Contribution.objects.create(
            addon_id=self.addon.id,
            amount=self.price.price,
            uuid='<some uuid>',
            type=amo.CONTRIB_PENDING,
            user=self.user
        )
        self.buyer_email = 'buyer@example.com'
        self.webpay_dev_id = '<stored in solitude>'
        self.webpay_dev_secret = '<stored in solitude>'

        solitude_patcher = mock.patch('mkt.purchase.webpay.solitude')
        self.solitude = solitude_patcher.start()
        self.addCleanup(solitude_patcher.stop)

        (self.solitude.api.generic.transaction.get_object_or_404
                                              .return_value) = {
            'buyer': 'buyer-uri',
        }

        self.solitude_by_url = mock.MagicMock()
        self.solitude.api.by_url.return_value = self.solitude_by_url
        self.solitude_by_url.get_object_or_404.return_value = {
            'email': self.buyer_email,
        }

    def post(self, req=None):
        if not req:
            req = self.jwt()
        return self.client.post(reverse('webpay.postback'),
                                data={'notice': req})

    def jwt_dict(self, expiry=3600, issued_at=None, contrib_uuid=None):
        if not issued_at:
            issued_at = calendar.timegm(time.gmtime())
        if not contrib_uuid:
            contrib_uuid = self.contrib.uuid
        return {
            'iss': 'mozilla',
            'aud': self.webpay_dev_id,
            'typ': 'mozilla/payments/inapp/v1',
            'iat': issued_at,
            'exp': issued_at + expiry,
            'request': {
                'name': 'Some App',
                'description': 'fantastic app',
                'pricePoint': '1',
                'currencyCode': 'USD',
                'postbackURL': '/postback',
                'chargebackURL': '/chargeback',
                'productData': 'contrib_uuid=%s' % contrib_uuid
            },
            'response': {
                'transactionID': '<webpay-trans-id>',
                'price': {'amount': '10.99', 'currency': 'BRL'}
            },
        }

    def jwt(self, req=None, **kw):
        if not req:
            req = self.jwt_dict(**kw)
        return jwt.encode(req, self.webpay_dev_secret)

    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_valid(self, decode, tasks):
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict
        resp = self.post(req=jwt_encoded)
        decode.assert_called_with(jwt_encoded, ANY)
        eq_(resp.status_code, 200)
        eq_(resp.content, '<webpay-trans-id>')
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, amo.CONTRIB_PURCHASE)
        eq_(cn.transaction_id, '<webpay-trans-id>')
        eq_(cn.amount, Decimal('10.99'))
        eq_(cn.currency, 'BRL')
        tasks.send_purchase_receipt.delay.assert_called_with(cn.pk)

    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_user_created_after_purchase(self, decode, tasks):
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict
        self.contrib.user = None
        self.contrib.save()
        eq_(UserProfile.objects.filter(email=self.buyer_email).count(), 0)
        resp = self.post(req=jwt_encoded)
        eq_(resp.status_code, 200)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        user = UserProfile.objects.get(email=self.buyer_email)
        eq_(cn.user, user)
        eq_(cn.user.source, amo.LOGIN_SOURCE_WEBPAY)

    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_valid_duplicate(self, decode, tasks):
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict

        self.contrib.update(type=amo.CONTRIB_PURCHASE,
                            transaction_id='<webpay-trans-id>')

        resp = self.post(req=jwt_encoded)
        eq_(resp.status_code, 200)
        eq_(resp.content, '<webpay-trans-id>')
        assert not tasks.send_purchase_receipt.delay.called

    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_invalid_duplicate(self, decode, tasks):
        jwt_dict = self.jwt_dict()
        jwt_dict['response']['transactionID'] = '<some-other-trans-id>'
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict

        self.contrib.update(type=amo.CONTRIB_PURCHASE,
                            transaction_id='<webpay-trans-id>')

        with self.assertRaises(LookupError):
            self.post(req=jwt_encoded)

        assert not tasks.send_purchase_receipt.delay.called

    def test_invalid(self, tasks):
        resp = self.post()
        eq_(resp.status_code, 400)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, amo.CONTRIB_PENDING)

    def test_empty_notice(self, tasks):
        resp = self.client.post(reverse('webpay.postback'), data={})
        eq_(resp.status_code, 400)

    @raises(RequestExpired)
    @fudge.patch('lib.crypto.webpay.jwt.decode')
    def test_invalid_claim(self, tasks, decode):
        iat = calendar.timegm(time.gmtime()) - 3601  # too old
        decode.expects_call().returns(self.jwt_dict(issued_at=iat))
        self.post()

    @raises(LookupError)
    @fudge.patch('mkt.purchase.webpay.parse_from_webpay')
    def test_unknown_contrib(self, tasks, parse_from_webpay):
        example = self.jwt_dict()
        example['request']['productData'] = 'contrib_uuid=<bogus>'

        parse_from_webpay.expects_call().returns(example)
        self.post()

    @raises(LookupError)
    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_no_transaction_found_fails(self, decode, tasks):
        (self.solitude.api.generic.transaction
                                  .get_object_or_404
                                  .side_effect) = ObjectDoesNotExist
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict
        self.post(req=jwt_encoded)

    @raises(LookupError)
    @mock.patch('lib.crypto.webpay.jwt.decode')
    def test_no_buyer_found_fails(self, decode, tasks):
        self.solitude_by_url.get_object_or_404.side_effect = ObjectDoesNotExist
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        decode.return_value = jwt_dict
        self.post(req=jwt_encoded)
