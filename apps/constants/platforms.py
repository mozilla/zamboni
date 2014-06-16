from tower import ugettext_lazy as _


class PLATFORM_ALL:
    id = 1
    name = _(u'All Platforms')
    shortname = 'all'
    api_name = u'ALL'


PLATFORMS = {PLATFORM_ALL.id: PLATFORM_ALL}
