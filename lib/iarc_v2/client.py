# -*- coding: utf8 -*-
import datetime
import json
import requests
from urlparse import urljoin

import commonware.log
from django.conf import settings

from lib.iarc_v2.serializers import IARCV2RatingListSerializer


log = commonware.log.getLogger('z.iarc_v2')


def get_rating_changes():
    """
    GetRatingChange for all changes within the last day.

    TODO: Could add support for pagination, but very low priority since we
          will never ever get anywhere close to 500 rating changes in a single
          day.
    """
    if settings.IARC_V2_MOCK:
        return json.loads(file('./mock/GetRatingChanges.json').read())
    else:
        start_date = datetime.datetime.utcnow()
        end_date = start_date - datetime.timedelta(days=1)
        url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'GetRatingChanges', {
            'StartDate': start_date.strftime('%Y-%m-%d'),
            'EndDate': end_date.strftime('%Y-%m-%d'),
            'MaxRows': 500,  # Limit.
            'StartRowIndex': 0  # Offset.
        })
        return requests.get(url).json()


def publish_cert(cert_id):
    _update_certs(cert_id, 'Publish')


def remove_cert(cert_id):
    _update_certs(cert_id, 'RemoveProduct')


def search_certs(cert_id):
    """SearchCerts for complete data on a single certificate."""
    data = None
    if settings.IARC_V2_MOCK:
        data = json.loads(file('./mock/SearchCerts.json').read())
    else:
        url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'SearchCerts')
        data = requests.get(url, {'CertID': cert_id}).json()
    return IARCV2RatingListSerializer(data=data).data


def _update_certs(cert_id, action):
    """
    UpdateCerts to tell IARC when we publish or unpublish a product.
    Endpoint can handle batch updates, but we only need one at a time.

    Arguments:
    cert_id -- Globally unique ID for certificate.
    action -- One of [InvalidateCert, RemoveProduct, UpdateStoreAttributes,
                      Publish].

    Return:
    Update object.
        ResultCode (string) -- Success or Failure
        ErrorId (string) -- Can pass on to IARC for debugging.
        ErrorMessage (string) -- Human-readable error message
    """
    if settings.IARC_V2_MOCK:
        return json.loads(file('./mock/UpdateCerts.json').read())
    else:
        url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'UpdateCerts', {
            'UpdateList': [{
                'CertID': cert_id,
                'Action': action
            }]
        })
        return requests.post(url).json()
