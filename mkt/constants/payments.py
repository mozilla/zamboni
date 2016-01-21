# -*- coding: utf-8 -*-
from tower import ugettext_lazy as _
from lib.constants import ALL_CURRENCIES

# Source, PayPal docs, PP_AdaptivePayments.PDF
PAYPAL_CURRENCIES = ['AUD', 'BRL', 'CAD', 'CHF', 'CZK', 'DKK', 'EUR', 'GBP',
                     'HKD', 'HUF', 'ILS', 'JPY', 'MXN', 'MYR', 'NOK', 'NZD',
                     'PHP', 'PLN', 'SEK', 'SGD', 'THB', 'TWD', 'USD']
PAYPAL_CURRENCIES = dict((k, ALL_CURRENCIES[k]) for k in PAYPAL_CURRENCIES)

# TODO(Kumar) bug 768223. Need to find a more complete list for this.
# This is just a sample.
LOCALE_CURRENCY = {
    'en_US': 'USD',
    'en_CA': 'CAD',
    'it': 'EUR',
    'fr': 'EUR',
    'pt_BR': 'BRL',
}

CURRENCY_DEFAULT = 'USD'

CONTRIB_VOLUNTARY = 0
CONTRIB_PURCHASE = 1
CONTRIB_REFUND = 2
CONTRIB_CHARGEBACK = 3
# We've started a transaction and we need to wait to see what
# paypal will return.
CONTRIB_PENDING = 4
# The following in-app contribution types are deprecated. Avoid re-using
# these ID numbers in new types.
_CONTRIB_INAPP_PENDING = 5
_CONTRIB_INAPP = 6
# The app was temporarily free. This is so we can record it in
# the purchase table, even though there isn't a contribution.
CONTRIB_NO_CHARGE = 7
CONTRIB_OTHER = 99

CONTRIB_TYPES = {
    CONTRIB_CHARGEBACK: _('Chargeback'),
    CONTRIB_OTHER: _('Other'),
    CONTRIB_PURCHASE: _('Purchase'),
    CONTRIB_REFUND: _('Refund'),
    CONTRIB_VOLUNTARY: _('Voluntary'),
}

MKT_TRANSACTION_CONTRIB_TYPES = {
    CONTRIB_CHARGEBACK: _('Chargeback'),
    CONTRIB_PURCHASE: _('Purchase'),
    CONTRIB_REFUND: _('Refund'),
}

CONTRIB_TYPE_DEFAULT = CONTRIB_VOLUNTARY

REFUND_PENDING = 0  # Just to irritate you I didn't call this REFUND_REQUESTED.
REFUND_APPROVED = 1
REFUND_APPROVED_INSTANT = 2
REFUND_DECLINED = 3
REFUND_FAILED = 4

REFUND_STATUSES = {
    # Refund pending (purchase > 30 min ago).
    REFUND_PENDING: _('Pending'),

    # Approved manually by developer.
    REFUND_APPROVED: _('Approved'),

    # Instant refund (purchase <= 30 min ago).
    REFUND_APPROVED_INSTANT: _('Approved Instantly'),

    # Declined manually by developer.
    REFUND_DECLINED: _('Declined'),

    # Refund didn't work somehow.
    REFUND_FAILED: _('Failed'),
}

PAYMENT_DETAILS_ERROR = {
    'CREATED': _('The payment was received, but not completed.'),
    'INCOMPLETE': _('The payment was received, but not completed.'),
    'ERROR': _('The payment failed.'),
    'REVERSALERROR': _('The reversal failed.'),
    'PENDING': _('The payment was received, but not completed '
                 'and is awaiting processing.'),
}

PROVIDER_PAYPAL = 0
PROVIDER_BANGO = 1
PROVIDER_REFERENCE = 2

PROVIDER_CHOICES = (
    (PROVIDER_PAYPAL, 'paypal'),
    (PROVIDER_BANGO, 'bango'),
    (PROVIDER_REFERENCE, 'reference'),
)

PROVIDER_LOOKUP = dict(PROVIDER_CHOICES)
PROVIDER_LOOKUP_INVERTED = dict([(v, k) for k, v in PROVIDER_CHOICES])
CARRIER_CHOICES = ()

# Payment methods accepted by the PriceCurrency..
#
# If we ever go beyond these two payment methods, we might need to do
# something more scalable.
PAYMENT_METHOD_OPERATOR = 0
PAYMENT_METHOD_CARD = 1
PAYMENT_METHOD_ALL = 2

PAYMENT_METHOD_CHOICES = (
    (PAYMENT_METHOD_OPERATOR, 'operator'),
    (PAYMENT_METHOD_CARD, 'card'),
    (PAYMENT_METHOD_ALL, 'operator+card')
)

PENDING = 'PENDING'
COMPLETED = 'OK'
FAILED = 'FAILED'
SOLITUDE_REFUND_STATUSES = {
    PENDING: _('Pending'),
    COMPLETED: _('Completed'),
    FAILED: _('Failed'),
}

# SellerProduct access types.
ACCESS_PURCHASE = 1
ACCESS_SIMULATE = 2

PAYMENT_STATUSES = {
    1: 'passed',
    2: 'failed'
}
