from django.conf.urls import include, patterns

from mkt.purchase.urls import app_purchase_patterns
from mkt.receipts.urls import app_receipt_patterns


urlpatterns = patterns(
    '',
    # Merge app purchase / receipt patterns.
    ('^purchase/', include(app_purchase_patterns)),
    ('^purchase/', include(app_receipt_patterns)),
)
