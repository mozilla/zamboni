import calendar
import json
import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse

import jwt
import mock
from mock import ANY
from mozpay.exc import RequestExpired
from nose.tools import eq_, raises

import mkt
from mkt.api.exceptions import AlreadyPurchased
from mkt.inapp.models import InAppProduct
from mkt.prices.models import AddonPurchase, Price
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
                                                   type=mkt.CONTRIB_PENDING,
                                                   user=self.user)

        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, uuid]))

        eq_(data['status'], 'incomplete')

        contribution.update(type=mkt.CONTRIB_PURCHASE)

        data = self.get(reverse('webpay.pay_status',
                                args=[self.addon.app_slug, uuid]))

        eq_(data['status'], 'complete')

    def test_status_for_purchases_only(self):
        uuid = '<returned from prepare-pay>'
        Contribution.objects.create(addon_id=self.addon.id,
                                    amount=self.price.price,
                                    uuid=uuid,
                                    type=mkt.CONTRIB_PURCHASE,
                                    user=self.user)
        self.client.logout()
        self.login('admin@mozilla.com')
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
                                     type=mkt.CONTRIB_PURCHASE)

        with self.assertRaises(AlreadyPurchased):
            self.client.post(self.prepare_pay)

    def test_require_login(self):
        self.client.logout()
        resp = self.client.post(self.prepare_pay)
        self.assertLoginRequired(resp)


@mock.patch.object(settings, 'SOLITUDE_HOSTS', ['host'])
class PostbackTest(PurchaseTest):

    def setUp(self):
        super(PostbackTest, self).setUp()
        self.client.logout()
        self.contrib = Contribution.objects.create(
            addon_id=self.addon.id,
            amount=self.price.price,
            uuid='<some uuid>',
            type=mkt.CONTRIB_PENDING,
            user=self.user
        )
        self.buyer_email = 'buyer@example.com'
        self.webpay_dev_id = '<stored in solitude>'
        self.webpay_dev_secret = '<stored in solitude>'
        p = mock.patch.object(settings, 'APP_PURCHASE_SECRET',
                              self.webpay_dev_secret)
        p.start()
        self.addCleanup(p.stop)

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

        p = mock.patch('mkt.purchase.webpay.tasks')
        self.tasks = p.start()
        self.addCleanup(p.stop)

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
                # Return ID as a Unicode object just like real in life.
                # This is here to protect against subtle string coercion
                # regressions!
                'transactionID': u'<webpay-trans-id>',
                'price': {'amount': '10.99', 'currency': 'BRL'}
            },
        }

    def jwt(self, req=None, encoding_secret=None, encode_kw=None, **kw):
        req = req or self.jwt_dict(**kw)
        encode_kw = encode_kw or {}
        encoding_secret = encoding_secret or self.webpay_dev_secret
        return jwt.encode(req, encoding_secret, **encode_kw)


class TestPostbackWithDecoding(PostbackTest):

    def test_valid_notice(self):
        resp = self.post()
        eq_(resp.status_code, 200)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, mkt.CONTRIB_PURCHASE)

    def test_invalid_signature(self):
        jwt_encoded = self.jwt(req=self.jwt_dict(), encoding_secret='nope')
        resp = self.post(req=jwt_encoded)
        eq_(resp.status_code, 400)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, mkt.CONTRIB_PENDING)

    def test_empty_notice(self):
        resp = self.client.post(reverse('webpay.postback'), data={})
        eq_(resp.status_code, 400)

    def test_unsupported_algorithm(self):
        # Create a JWT with an algorithm that is not explicitly allowed.
        jwt_encoded = self.jwt(req=self.jwt_dict(),
                               encode_kw={'algorithm': 'HS256'})
        with self.settings(SUPPORTED_JWT_ALGORITHMS=['RS512']):
            resp = self.post(req=jwt_encoded)
        eq_(resp.status_code, 400)


class TestPostback(PostbackTest):

    def setUp(self):
        super(TestPostback, self).setUp()

        p = mock.patch('lib.crypto.webpay.jwt.decode')
        self.decode = p.start()
        self.addCleanup(p.stop)

    def post(self, *args, **kw):
        fake_decode = kw.pop('fake_decode', False)
        if fake_decode:
            jwt_dict = self.jwt_dict()
            jwt_encoded = self.jwt(req=jwt_dict)
            self.decode.return_value = jwt_dict
            kw['req'] = jwt_encoded

        return super(TestPostback, self).post(*args, **kw)

    def test_valid(self):
        jwt_dict = self.jwt_dict()
        jwt_encoded = self.jwt(req=jwt_dict)
        self.decode.return_value = jwt_dict
        resp = self.post(req=jwt_encoded)
        self.decode.assert_called_with(
            jwt_encoded, ANY, algorithms=settings.SUPPORTED_JWT_ALGORITHMS)
        eq_(resp.status_code, 200)
        eq_(resp.content, '<webpay-trans-id>')
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, mkt.CONTRIB_PURCHASE)
        eq_(cn.transaction_id, '<webpay-trans-id>')
        eq_(cn.amount, Decimal('10.99'))
        eq_(cn.currency, 'BRL')
        self.tasks.send_purchase_receipt.delay.assert_called_with(cn.pk)

    def test_valid_in_app_product(self):
        inapp = InAppProduct.objects.create(
            logo_url='logo.png', name=u'Ivan Krsti\u0107',
            price=self.price, webapp=self.addon)
        self.contrib.update(inapp_product=inapp, addon=inapp.webapp,
                            user=self.user)
        jwt_dict = self.jwt_dict()
        self.decode.return_value = jwt_dict

        resp = self.post(req=self.jwt(req=jwt_dict))

        eq_(resp.status_code, 200)
        eq_(resp.content, '<webpay-trans-id>')

        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.transaction_id, '<webpay-trans-id>')

        self.tasks.send_purchase_receipt.delay.assert_called_with(cn.pk)

    def test_simulation(self):
        inapp = InAppProduct.objects.create(
            name='Test Product',
            price=Price.objects.all()[0],
            simulate=json.dumps({'result': 'postback'}))
        self.contrib.update(inapp_product=inapp, addon=None,
                            user=None)

        # Because Webpay doesn't make a real Solitude transaction for
        # simulations, we'll get a 404 when looking it up by ID.
        get = self.solitude.api.generic.transaction.get_object_or_404
        get.side_effect = ObjectDoesNotExist

        response_trans_id = '<simulate-uuid>'
        jwt_dict = self.jwt_dict()
        jwt_dict['response']['transactionID'] = response_trans_id
        jwt_encoded = self.jwt(req=jwt_dict)
        self.decode.return_value = jwt_dict
        resp = self.post(req=jwt_encoded)

        eq_(resp.status_code, 200)
        eq_(resp.content, response_trans_id)

        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, mkt.CONTRIB_PURCHASE)

        assert not self.tasks.send_purchase_receipt.delay.called

    def test_free_inapp(self):
        response_trans_id = '<free-uuid>'
        (self.solitude.api.generic.buyer.get_object_or_404
                                        .return_value) = {
            'email': self.buyer_email,
        }
        inapp = InAppProduct.objects.create(
            logo_url='logo.png', name=u'Free Inapp Product',
            price=Price.objects.get(price=0),
            webapp=self.addon)
        self.contrib.update(inapp_product=inapp, addon=inapp.webapp)
        jwt_dict = self.jwt_dict()
        jwt_dict['response']['transactionID'] = response_trans_id
        jwt_dict['response']['solitude_buyer_uuid'] = '<buyer:uuid>'
        jwt_dict['request']['pricePoint'] = '0'
        jwt_encoded = self.jwt(req=jwt_dict)
        self.decode.return_value = jwt_dict
        resp = self.post(req=jwt_encoded)
        (self.solitude.api.generic.buyer
             .get_object_or_404.assert_called_with)(uuid='<buyer:uuid>')
        eq_(resp.status_code, 200)
        eq_(resp.content, response_trans_id)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        eq_(cn.type, mkt.CONTRIB_PURCHASE)
        eq_(cn.user.email, self.buyer_email)
        self.tasks.send_purchase_receipt.delay.assert_called_with(cn.pk)

    def test_user_created_after_purchase(self):
        self.contrib.user = None
        self.contrib.save()
        eq_(UserProfile.objects.filter(email=self.buyer_email).count(), 0)
        resp = self.post(fake_decode=True)
        eq_(resp.status_code, 200)
        cn = Contribution.objects.get(pk=self.contrib.pk)
        user = UserProfile.objects.get(email=self.buyer_email)
        eq_(cn.user, user)
        eq_(cn.user.source, mkt.LOGIN_SOURCE_WEBPAY)

    def test_valid_duplicate(self):
        self.contrib.update(type=mkt.CONTRIB_PURCHASE,
                            transaction_id='<webpay-trans-id>')

        resp = self.post(fake_decode=True)
        eq_(resp.status_code, 200)
        eq_(resp.content, '<webpay-trans-id>')
        assert not self.tasks.send_purchase_receipt.delay.called

    def test_invalid_duplicate(self):
        jwt_dict = self.jwt_dict()
        jwt_dict['response']['transactionID'] = '<some-other-trans-id>'
        jwt_encoded = self.jwt(req=jwt_dict)
        self.decode.return_value = jwt_dict

        self.contrib.update(type=mkt.CONTRIB_PURCHASE,
                            transaction_id='<webpay-trans-id>')

        with self.assertRaises(LookupError):
            self.post(req=jwt_encoded)

        assert not self.tasks.send_purchase_receipt.delay.called

    @raises(RequestExpired)
    def test_invalid_claim(self):
        iat = calendar.timegm(time.gmtime()) - 3601  # too old
        self.decode.return_value = self.jwt_dict(issued_at=iat)
        self.post()

    @raises(LookupError)
    @mock.patch('mkt.purchase.webpay.parse_from_webpay')
    def test_unknown_contrib(self, parse_from_webpay):
        example = self.jwt_dict()
        example['request']['productData'] = 'contrib_uuid=<bogus>'

        parse_from_webpay.return_value = example
        self.post()

    @raises(LookupError)
    def test_no_transaction_found_fails(self):
        (self.solitude.api.generic.transaction
                                  .get_object_or_404
                                  .side_effect) = ObjectDoesNotExist
        self.post(fake_decode=True)

    @raises(LookupError)
    def test_no_buyer_found_fails(self):
        self.solitude_by_url.get_object_or_404.side_effect = ObjectDoesNotExist
        self.post(fake_decode=True)
