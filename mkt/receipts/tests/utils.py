import calendar
import time
from urllib import urlencode


def get_sample_app_receipt():
    return {
        'user': {
            'type': 'directed-identifier',
            'value': 'some-uuid'
        },
        'product': {
            'url': 'http://f.com',
            'storedata': urlencode({'id': 337141})
        },
        'verify': 'https://foo.com/verifyme/',
        'detail': 'https://foo.com/detail/',
        'reissue': 'https://foo.com/reissue/',
        'iss': 'https://foo.com',
        'iat': calendar.timegm(time.gmtime()),
        'nbf': calendar.timegm(time.gmtime()),
        'exp': calendar.timegm(time.gmtime()) + 1000,
        'typ': 'purchase-receipt'
    }


def get_sample_inapp_receipt(contribution):
    sample_receipt = get_sample_app_receipt()
    sample_receipt['user']['value'] = 'anonymous-user'
    sample_receipt['product']['storedata'] = urlencode({
        'id': 337141,
        'contrib': contribution.pk,
    })
    return sample_receipt
