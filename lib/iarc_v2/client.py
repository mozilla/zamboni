# -*- coding: utf8 -*-
import datetime
import requests
from urlparse import urljoin
from uuid import UUID

from django.conf import settings
from django.db import transaction

import commonware.log
from post_request_task.task import task

from lib.iarc_v2.serializers import IARCV2RatingListSerializer
from mkt.site.helpers import absolutify
from mkt.translations.utils import no_translation
from mkt.users.models import UserProfile

log = commonware.log.getLogger('z.iarc_v2')


class IARCException(Exception):
    pass


def _iarc_headers():
    """HTTP headers to include in each request to IARC."""
    return {
        'StoreID': settings.IARC_V2_STORE_ID,
        'StorePassword': settings.IARC_V2_STORE_PASSWORD,
    }


def _iarc_request(endpoint_name, data):
    """Wrapper around requests.post which handles url generation from the
    endpoint_name and auth headers. Returns data as a dict."""
    url = urljoin(settings.IARC_V2_SERVICE_ENDPOINT, endpoint_name)
    headers = _iarc_headers()
    response = requests.post(url, headers=headers, json=data)
    try:
        value = response.json()
    except ValueError:
        value = {}
    return value


def _iarc_app_data(app):
    """App data that IARC needs in PushCert response / AttachToCert request."""
    from mkt.webapps.models import Webapp

    author = app.listed_authors[0] if app.listed_authors else UserProfile()
    with no_translation(app.default_locale):
        app_name = unicode(Webapp.with_deleted.get(pk=app.pk).name)
    data = {
        'Publish': app.is_public(),
        'ProductName': app_name,
        'StoreProductID': app.guid,
        'StoreProductURL': absolutify(app.get_url_path()),
        # We want an identifier that does not change when users attached to
        # an app are shuffled around, so just use the app PK as developer id.
        'StoreDeveloperID': app.pk,
        # PushCert and AttachToCert docs use a different property for the
        # developer email address, use both just in case.
        'DeveloperEmail': author.email,
        'EmailAddress': author.email,
        'CompanyName': app.developer_name,
    }
    return data


def get_rating_changes(date=None):
    """
    Call GetRatingChange to get all changes from IARC within 24 hours of the
    specified date (using today by default), and apply them to the
    corresponding Webapps.

    FIXME: Could add support for pagination, but very low priority since we
    will never ever get anywhere close to 500 rating changes in a single day.
    """
    from mkt.webapps.models import IARCCert

    # EndDate should be the most recent one.
    end_date = date or datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=1)
    log.info('Calling IARC GetRatingChanges from %s to %s',
             start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    data = _iarc_request('GetRatingChanges', {
        'StartDate': start_date.strftime('%Y-%m-%d'),
        'EndDate': end_date.strftime('%Y-%m-%d'),
        'MaxRows': 500,  # Limit.
        'StartRowIndex': 0  # Offset.
    })
    for row in data.get('CertList', []):
        # Find app through Cert ID, ignoring unknown certs.
        try:
            cert = IARCCert.objects.get(cert_id=UUID(row['CertID']).get_hex())
        except IARCCert.DoesNotExist:
            continue
        serializer = IARCV2RatingListSerializer(instance=cert.app, data=row)
        if serializer.is_valid():
            rating_bodies = [body.id for body
                             in serializer.validated_data['ratings'].keys()]
            serializer.save(rating_bodies=rating_bodies)
    return data


@transaction.atomic
def search_and_attach_cert(app, cert_id):
    """Call SearchCerts to get all info about an existing cert from IARC and
    apply that info to the Webapp instance passed. Then, call AttachToCert
    to notify IARC that we're attaching the cert to that Webapp."""
    serializer = search_cert(app, cert_id)
    if serializer.is_valid():
        serializer.save()
    else:
        raise IARCException('SearchCerts failed, invalid data!')
    data = _attach_to_cert(app, cert_id)
    if data.get('ResultCode') != 'Success':
        # If AttachToCert failed, we need to rollback the save we did earlier,
        # we raise an exception to do that since we are in an @atomic block.
        raise IARCException(data.get('ErrorMessage', 'AttachToCert failed!'))
    return data


def search_cert(app, cert_id):
    """Ask IARC for information about a cert."""
    log.info('Calling IARC SearchCert for app %s, cert %s',
             app.pk, unicode(UUID(cert_id)))
    data = _iarc_request('SearchCerts', {'CertID': unicode(UUID(cert_id))})
    # We don't care about MatchFound, serializer won't find the right fields
    # if no match is found.
    serializer = IARCV2RatingListSerializer(instance=app, data=data)
    return serializer


def _attach_to_cert(app, cert_id):
    """Tell IARC to attach a cert to an app."""
    data = _iarc_app_data(app)
    data['CertID'] = unicode(UUID(cert_id))
    log.info('Calling IARC AttachToCert for app %s, cert %s',
             app.pk, data['CertID'])
    return _iarc_request('AttachToCert', data)


@task
def publish(app_id):
    """Delayed task to tell IARC we published an app."""
    from mkt.webapps.models import IARCCert, Webapp

    try:
        app = Webapp.with_deleted.get(pk=app_id)
    except Webapp.DoesNotExist:
        return
    try:
        cert_id = app.iarc_cert.cert_id
        data = _update_certs(app_id, cert_id, 'Publish')
    except IARCCert.DoesNotExist:
        data = None
    return data


@task
def unpublish(app_id):
    """Delayed task to tell IARC we unpublished an app."""
    from mkt.webapps.models import IARCCert, Webapp

    try:
        app = Webapp.with_deleted.get(pk=app_id)
    except Webapp.DoesNotExist:
        return
    try:
        cert_id = app.iarc_cert.cert_id
        data = _update_certs(app_id, cert_id, 'Unpublish')
    except IARCCert.DoesNotExist:
        data = None
    return data


def refresh(app):
    """Refresh an app IARC information by asking IARC about its certificate."""
    serializer = search_cert(app, app.iarc_cert.cert_id)
    serializer.save()


# FIXME: implement UpdateStoreAttributes for when the app developer email
# changes.


def _update_certs(app_id, cert_id, action):
    """
    UpdateCerts to tell IARC when we publish or unpublish a product.
    Endpoint can handle batch updates, but we only need one at a time.

    Arguments:
    cert_id -- Globally unique ID for certificate.
    action -- One of [InvalidateCert, Unpublish, UpdateStoreAttributes,
                      Publish].

    Return:
    Update object.
        ResultCode (string) -- Success or Failure
        ErrorId (string) -- Can pass on to IARC for debugging.
        ErrorMessage (string) -- Human-readable error message
    """
    data = {
        'UpdateList': [{
            'CertID': unicode(UUID(cert_id)),
            'Action': action,
        }]
    }
    log.info('Calling IARC UpdateCert %s for app %s, cert %s',
             action, app_id, data['UpdateList'][0]['CertID'])
    return _iarc_request('UpdateCerts', data)
