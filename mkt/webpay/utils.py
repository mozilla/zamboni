from django.conf import settings

import bleach


def strip_tags(text):
    # Until atob() supports encoded HTML we are stripping all tags.
    # See bug 83152422
    return bleach.clean(unicode(text), strip=True, tags=[])


def make_external_id(product):
    """
    Generates a webpay/solitude external ID given an webapp's primary key.
    """
    # This namespace is currently necessary because app products
    # are mixed into an application's own in-app products.
    # Maybe we can fix that.
    # Also, we may use various dev/stage servers with the same
    # Bango test API.
    domain = getattr(settings, 'DOMAIN', None)
    if not domain:
        domain = 'marketplace-dev'
    external_id = domain.split('.')[0]
    return '{0}:{1}'.format(external_id, product.pk)
