# -*- coding: utf8 -*-
import datetime
import requests
from urlparse import urljoin
from uuid import UUID

import commonware.log
from django.conf import settings

from lib.iarc_v2.serializers import IARCV2RatingListSerializer
from mkt.webapps.models import IARCCert

log = commonware.log.getLogger('z.iarc_v2')


def get_rating_changes():
    """
    Call GetRatingChange to get all changes from IARC within the last day, and
    apply them to the corresponding Webapps.

    FIXME: Could add support for pagination, but very low priority since we
    will never ever get anywhere close to 500 rating changes in a single day.
    """
    start_date = datetime.datetime.utcnow()
    end_date = start_date - datetime.timedelta(days=1)
    url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'GetRatingChanges', {
        'StartDate': start_date.strftime('%Y-%m-%d'),
        'EndDate': end_date.strftime('%Y-%m-%d'),
        'MaxRows': 500,  # Limit.
        'StartRowIndex': 0  # Offset.
    })
    data = requests.get(url).json()
    for row in data.get('CertList', []):
        # Find app through Cert ID, ignoring unknown certs.
        try:
            cert = IARCCert.objects.get(cert_id=UUID(row['CertID']).get_hex())
        except IARCCert.DoesNotExist:
            continue
        serializer = IARCV2RatingListSerializer(instance=cert.app, data=row)
        if serializer.is_valid():
            serializer.save()
    return data


def publish(app):
    """Tell IARC we published an app."""
    try:
        cert_id = app.iarc_cert.cert_id
        data = _update_certs(cert_id, 'Publish')
    except IARCCert.DoesNotExist:
        data = None
    return data


def unpublish(app):
    """Tell IARC we unpublished an app."""
    try:
        cert_id = app.iarc_cert.cert_id
        data = _update_certs(cert_id, 'RemoveProduct')
    except IARCCert.DoesNotExist:
        data = None
    return data


# FIXME: implement UpdateStoreAttributes for when the app developer email
# changes. Need to use a StoreDeveloperID that would have been returned by
# PushCert/AttachToCert.


def search_and_attach_cert(app, cert_id):
    """Call SearchCerts to get all info about an existing cert from IARC and
    apply that info to the Webapp instance passed.

    FIXME: also call AttachToCert to tell IARC we attached the app."""
    url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'SearchCerts')
    data = requests.get(url, {'CertID': unicode(UUID(cert_id))}).json()
    serializer = IARCV2RatingListSerializer(instance=app, data=data)
    if serializer.is_valid():
        serializer.save()
    # FIXME: call AttachToCert here. We should probably wrap the whole function
    # in an atomic block, to rollback if AttachToCert fails.
    return data


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
    url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, 'UpdateCerts')
    data = {
        'UpdateList': [{
            'CertID': unicode(UUID(cert_id)),
            'Action': action,
        }]
    }
    return requests.post(url, data=data).json()
