import calendar
import json
from datetime import datetime
import sys
from time import gmtime, time
from urlparse import parse_qsl, urlparse
from wsgiref.handlers import format_date_time

import jwt
from browserid.errors import ExpiredSignatureError
from django_statsd.clients import statsd
from receipts import certs

from lib.cef_loggers import receipt_cef
from lib.crypto.receipt import sign
from lib.utils import static_url

from services.utils import settings

from utils import (CONTRIB_CHARGEBACK, CONTRIB_NO_CHARGE, CONTRIB_PURCHASE,
                   CONTRIB_REFUND, log_configure, log_exception, log_info,
                   mypool)

# Go configure the log.
log_configure()

# This has to be imported after the settings (utils).
import receipts  # noqa

status_codes = {
    200: '200 OK',
    204: '204 OK',
    405: '405 Method Not Allowed',
    500: '500 Internal Server Error',
}


class VerificationError(Exception):
    pass


class InvalidReceipt(Exception):
    """
    InvalidReceipt takes a message, which is then displayed back to the app so
    they can understand the failure.
    """
    pass


class RefundedReceipt(Exception):
    pass


class Verify:

    def __init__(self, receipt, environ):
        self.receipt = receipt
        self.environ = environ

        # This is so the unit tests can override the connection.
        self.conn, self.cursor = None, None

    def check_full(self):
        """
        This is the default that verify will use, this will
        do the entire stack of checks.
        """
        receipt_domain = urlparse(static_url('WEBAPPS_RECEIPT_URL')).netloc
        try:
            self.decoded = self.decode()
            self.check_type('purchase-receipt')
            self.check_url(receipt_domain)
            self.check_purchase()
        except InvalidReceipt, err:
            return self.invalid(str(err))
        except RefundedReceipt:
            return self.refund()

        return self.ok_or_expired()

    def check_without_purchase(self):
        """
        This is what the developer and reviewer receipts do, we aren't
        expecting a purchase, but require a specific type and install.
        """
        try:
            self.decoded = self.decode()
            self.check_type('developer-receipt', 'reviewer-receipt')
            self.check_url(settings.DOMAIN)
        except InvalidReceipt, err:
            return self.invalid(str(err))

        return self.ok_or_expired()

    def check_without_db(self, status):
        """
        This is what test receipts do, no purchase or install check.
        In this case the return is custom to the caller.
        """
        assert status in ['ok', 'expired', 'invalid', 'refunded']

        try:
            self.decoded = self.decode()
            self.check_type('test-receipt')
            self.check_url(settings.DOMAIN)
        except InvalidReceipt, err:
            return self.invalid(str(err))

        return getattr(self, status)()

    def decode(self):
        """
        Verifies that the receipt can be decoded and that the initial
        contents of the receipt are correct.

        If its invalid, then just return invalid rather than give out any
        information.
        """
        try:
            receipt = decode_receipt(self.receipt)
        except:
            exc_type, exc_value, tb = sys.exc_info()
            log_exception({'receipt': '%s...' % self.receipt[:10],
                           'app': self.get_app_id(raise_exception=False)})
            log_info('Error decoding receipt')
            raise InvalidReceipt('ERROR_DECODING'), None, tb

        try:
            assert receipt['user']['type'] == 'directed-identifier'
        except (AssertionError, KeyError):
            log_info('No directed-identifier supplied')
            raise InvalidReceipt('NO_DIRECTED_IDENTIFIER')

        return receipt

    def check_type(self, *types):
        """
        Verifies that the type of receipt is what we expect.
        """
        if self.decoded.get('typ', '') not in types:
            log_info('Receipt type not in %s' % ','.join(types))
            raise InvalidReceipt('WRONG_TYPE')

    def check_url(self, domain):
        """
        Verifies that the URL of the verification is what we expect.

        :param domain: the domain you expect the receipt to be verified at,
            note that "real" receipts are verified at a different domain
            from the main marketplace domain.
        """
        path = self.environ['PATH_INFO']
        parsed = urlparse(self.decoded.get('verify', ''))

        if parsed.netloc != domain:
            log_info('Receipt had invalid domain')
            raise InvalidReceipt('WRONG_DOMAIN')

        if parsed.path != path:
            log_info('Receipt had the wrong path')
            raise InvalidReceipt('WRONG_PATH')

    def get_user(self):
        """
        Attempt to retrieve the user information from the receipt.
        """
        try:
            return self.decoded['user']['value']
        except KeyError:
            # If somehow we got a valid receipt without a uuid
            # that's a problem. Log here.
            log_info('No user in receipt')
            raise InvalidReceipt('NO_USER')

    def get_storedata(self):
        """
        Attempt to retrieve the storedata information from the receipt.
        """
        try:
            storedata = self.decoded['product']['storedata']
            return dict(parse_qsl(storedata))
        except Exception, e:
            log_info('Invalid store data: {err}'.format(err=e))
            raise InvalidReceipt('WRONG_STOREDATA')

    def get_app_id(self, raise_exception=True):
        """
        Attempt to retrieve the app id from the storedata in the receipt.
        """
        try:
            return int(self.get_storedata()['id'])
        except Exception, e:
            if raise_exception:
                # There was some value for storedata but it was invalid.
                log_info('Invalid store data for app id: {err}'.format(
                    err=e))
                raise InvalidReceipt('WRONG_STOREDATA')

    def get_contribution_id(self):
        """
        Attempt to retrieve the contribution id
        from the storedata in the receipt.
        """
        try:
            return int(self.get_storedata()['contrib'])
        except Exception, e:
            # There was some value for storedata but it was invalid.
            log_info('Invalid store data for contrib id: {err}'.format(
                err=e))
            raise InvalidReceipt('WRONG_STOREDATA')

    def get_inapp_id(self):
        """
        Attempt to retrieve the inapp id
        from the storedata in the receipt.
        """
        return self.get_storedata()['inapp_id']

    def setup_db(self):
        """
        Establish a connection to the database.
        All database calls are done at a low level and avoid the
        Django ORM.
        """
        if not self.cursor:
            self.conn = mypool.connect()
            self.cursor = self.conn.cursor()

    def check_purchase(self):
        """
        Verifies that the app or inapp has been purchased.
        """
        storedata = self.get_storedata()
        if 'contrib' in storedata:
            self.check_purchase_inapp()
        else:
            self.check_purchase_app()

    def check_purchase_inapp(self):
        """
        Verifies that the inapp has been purchased.
        """
        self.setup_db()
        sql = """SELECT i.guid, c.type FROM stats_contributions c
                 JOIN inapp_products i ON i.id=c.inapp_product_id
                 WHERE c.id = %(contribution_id)s LIMIT 1;"""
        self.cursor.execute(
            sql,
            {'contribution_id': self.get_contribution_id()}
        )
        result = self.cursor.fetchone()
        if not result:
            log_info('Invalid in-app receipt, no purchase')
            raise InvalidReceipt('NO_PURCHASE')

        contribution_inapp_id, purchase_type = result
        self.check_purchase_type(purchase_type)
        self.check_inapp_product(contribution_inapp_id)

    def check_inapp_product(self, contribution_inapp_id):
        if contribution_inapp_id != self.get_inapp_id():
            log_info('Invalid receipt, inapp_id does not match')
            raise InvalidReceipt('NO_PURCHASE')

    def check_purchase_app(self):
        """
        Verifies that the app has been purchased by the user.
        """
        self.setup_db()
        sql = """SELECT type FROM webapp_purchase
                 WHERE webapp_id = %(app_id)s
                 AND uuid = %(uuid)s LIMIT 1;"""
        self.cursor.execute(sql, {'app_id': self.get_app_id(),
                                  'uuid': self.get_user()})
        result = self.cursor.fetchone()
        if not result:
            log_info('Invalid app receipt, no purchase')
            raise InvalidReceipt('NO_PURCHASE')

        self.check_purchase_type(result[0])

    def check_purchase_type(self, purchase_type):
        """
        Verifies that the purchase type is of a valid type.
        """
        if purchase_type in (CONTRIB_REFUND, CONTRIB_CHARGEBACK):
            log_info('Valid receipt, but refunded')
            raise RefundedReceipt

        elif purchase_type in (CONTRIB_PURCHASE, CONTRIB_NO_CHARGE):
            log_info('Valid receipt')
            return

        else:
            log_info('Valid receipt, but invalid contribution')
            raise InvalidReceipt('WRONG_PURCHASE')

    def invalid(self, reason=''):
        receipt_cef.log(
            self.environ,
            self.get_app_id(raise_exception=False),
            'verify',
            'Invalid receipt'
        )
        return {'status': 'invalid', 'reason': reason}

    def ok_or_expired(self):
        # This receipt is ok now let's check it's expiry.
        # If it's expired, we'll have to return a new receipt
        try:
            expire = int(self.decoded.get('exp', 0))
        except ValueError:
            log_info('Error with expiry in the receipt')
            return self.expired()

        now = calendar.timegm(gmtime()) + 10  # For any clock skew.
        if now > expire:
            log_info('This receipt has expired: %s UTC < %s UTC'
                     % (datetime.utcfromtimestamp(expire),
                        datetime.utcfromtimestamp(now)))
            return self.expired()

        return self.ok()

    def ok(self):
        return {'status': 'ok'}

    def refund(self):
        receipt_cef.log(
            self.environ,
            self.get_app_id(raise_exception=False),
            'verify',
            'Refunded receipt'
        )
        return {'status': 'refunded'}

    def expired(self):
        receipt_cef.log(
            self.environ,
            self.get_app_id(raise_exception=False),
            'verify',
            'Expired receipt'
        )
        if settings.WEBAPPS_RECEIPT_EXPIRED_SEND:
            self.decoded['exp'] = (calendar.timegm(gmtime()) +
                                   settings.WEBAPPS_RECEIPT_EXPIRY_SECONDS)
            # Log that we are signing a new receipt as well.
            receipt_cef.log(
                self.environ,
                self.get_app_id(raise_exception=False),
                'sign',
                'Expired signing request'
            )
            return {'status': 'expired',
                    'receipt': sign(self.decoded)}
        return {'status': 'expired'}


def get_headers(length):
    return [('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'POST'),
            ('Access-Control-Allow-Headers', 'content-type, x-fxpay-version'),
            ('Content-Type', 'application/json'),
            ('Content-Length', str(length)),
            ('Cache-Control', 'no-cache'),
            ('Last-Modified', format_date_time(time()))]


def decode_receipt(receipt):
    """
    Cracks the receipt using the private key. This will probably change
    to using the cert at some point, especially when we get the HSM.
    """
    with statsd.timer('services.decode'):
        if settings.SIGNING_SERVER_ACTIVE:
            verifier = certs.ReceiptVerifier(
                valid_issuers=settings.SIGNING_VALID_ISSUERS)
            try:
                result = verifier.verify(receipt)
            except ExpiredSignatureError:
                # Until we can do something meaningful with this, just ignore.
                return jwt.decode(receipt.split('~')[1], verify=False)
            if not result:
                raise VerificationError()
            return jwt.decode(receipt.split('~')[1], verify=False)
        else:
            key = jwt.rsa_load(settings.WEBAPPS_RECEIPT_KEY)
            raw = jwt.decode(receipt, key,
                             algorithms=settings.SUPPORTED_JWT_ALGORITHMS)
    return raw


def status_check(environ):
    output = ''
    # Check we can read from the users_install table, should be nice and
    # fast. Anything that fails here, connecting to db, accessing table
    # will be an error we need to know about.
    if not settings.SIGNING_SERVER_ACTIVE:
        return 500, 'SIGNING_SERVER_ACTIVE is not set'

    try:
        conn = mypool.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users_install ORDER BY id DESC LIMIT 1')
    except Exception, err:
        return 500, str(err)

    return 200, output


def receipt_check(environ):
    output = ''
    with statsd.timer('services.verify'):
        data = environ['wsgi.input'].read()
        try:
            verify = Verify(data, environ)
            return 200, json.dumps(verify.check_full())
        except:
            log_exception('<none>')
            return 500, ''
    return output


def application(environ, start_response):
    body = ''
    path = environ.get('PATH_INFO', '')
    if path == '/services/status/':
        status, body = status_check(environ)
    else:
        # Only allow POST per verifier spec but also OPTIONS for CORS.
        method = environ.get('REQUEST_METHOD')
        if method == 'POST':
            status, body = receipt_check(environ)
        elif method == 'OPTIONS':
            status = 204
        else:
            status = 405
    start_response(status_codes[status], get_headers(len(body)))
    return [body]
