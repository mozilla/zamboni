from tower import ugettext_lazy as _lazy


COLLECTIONS_TYPE_BASIC = 0  # Header graphic.
COLLECTIONS_TYPE_FEATURED = 1  # No header graphic.
COLLECTIONS_TYPE_OPERATOR = 2  # Different graphic.

COLLECTION_TYPES = (
    (COLLECTIONS_TYPE_BASIC, _lazy(u'Basic Collection')),
    (COLLECTIONS_TYPE_FEATURED, _lazy(u'Featured App List')),
    (COLLECTIONS_TYPE_OPERATOR, _lazy(u'Operator Shelf')),
)
