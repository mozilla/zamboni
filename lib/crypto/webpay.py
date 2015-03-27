import hashlib
import sys
import uuid

from django.conf import settings

import commonware.log
from mozpay.verify import verify_claims, verify_keys

import jwt


log = commonware.log.getLogger('z.crypto')


class InvalidSender(Exception):
    pass


def get_uuid():
    return 'webpay:%s' % hashlib.md5(str(uuid.uuid4())).hexdigest()


def sign_webpay_jwt(data):
    return jwt.encode(data, settings.APP_PURCHASE_SECRET)


def parse_from_webpay(signed_jwt, ip):
    try:
        data = jwt.decode(signed_jwt.encode('ascii'),
                          settings.APP_PURCHASE_SECRET,
                          algorithms=settings.SUPPORTED_JWT_ALGORITHMS)
    except Exception, e:
        exc_type, exc_value, tb = sys.exc_info()
        log.info('Received invalid webpay postback from IP %s: %s' %
                 (ip or '(unknown)', e), exc_info=True)
        raise InvalidSender(e), None, tb

    verify_claims(data)
    iss, aud, product_data, trans_id = verify_keys(
        data,
        ('iss', 'aud', 'request.productData', 'response.transactionID'))
    log.info('Received webpay postback JWT: iss:%s aud:%s '
             'trans_id:%s product_data:%s'
             % (iss, aud, trans_id, product_data))
    return data
