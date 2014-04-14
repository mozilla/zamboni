from tower import ugettext_lazy as _lazy


FEEDAPP_TYPE_ICON = 'icon'
FEEDAPP_TYPE_IMAGE = 'image'
FEEDAPP_TYPE_DESC = 'description'
FEEDAPP_TYPE_QUOTE = 'quote'
FEEDAPP_TYPE_PREVIEW = 'preview'

FEEDAPP_TYPES = (
    (FEEDAPP_TYPE_ICON, _lazy(u'Icon')),
    (FEEDAPP_TYPE_IMAGE, _lazy(u'Header Graphic')),
    (FEEDAPP_TYPE_DESC, _lazy(u'Description')),
    (FEEDAPP_TYPE_QUOTE, _lazy(u'Quote')),
    (FEEDAPP_TYPE_PREVIEW, _lazy(u'Screenshot')),
)
