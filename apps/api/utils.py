import re

from django.conf import settings
from django.utils.html import strip_tags

import amo
from amo.helpers import absolutify
from amo.urlresolvers import reverse
from amo.utils import urlparams, epoch


# For app version major.minor matching.
m_dot_n_re = re.compile(r'^\d+\.\d+$')


# TODO: Remove when apps/bandwagon/ and apps/discovery/ are removed.
def addon_to_dict(addon, disco=False, src='api'):
    """
    Renders an addon in JSON for the API.
    """
    v = addon.current_version
    url = lambda u, **kwargs: settings.SITE_URL + urlparams(u, **kwargs)

    if disco:
        learnmore = settings.SERVICES_URL + reverse('discovery.addons.detail',
                                                    args=[addon.slug])
        learnmore = urlparams(learnmore, src='discovery-personalrec')
    else:
        learnmore = url(addon.get_url_path(), src=src)

    d = {
        'id': addon.id,
        'name': unicode(addon.name) if addon.name else None,
        'guid': addon.guid,
        'status': amo.STATUS_CHOICES_API[addon.status],
        'type': amo.ADDON_SLUGS_UPDATE[addon.type],
        'authors': [{'id': a.id, 'name': unicode(a.name),
                     'link': absolutify(a.get_url_path(src=src))}
                    for a in addon.listed_authors],
        'summary': strip_tags(unicode(addon.summary)) if addon.summary else None,
        'description': strip_tags(unicode(addon.description)),
        'icon': addon.icon_url,
        'learnmore': learnmore,
        'reviews': url(addon.reviews_url),
        'total_dls': addon.total_downloads,
        'weekly_dls': addon.weekly_downloads,
        'adu': addon.average_daily_users,
        'created': epoch(addon.created),
        'last_updated': epoch(addon.last_updated),
        'homepage': unicode(addon.homepage) if addon.homepage else None,
        'support': unicode(addon.support_url) if addon.support_url else None,
    }
    if addon.is_persona():
        d['theme'] = addon.persona.theme_data

    if v:
        d['version'] = v.version
        d['platforms'] = [unicode(a.name) for a in v.supported_platforms]
        d['compatible_apps'] = v.compatible_apps.values()

    if addon.eula:
        d['eula'] = unicode(addon.eula)

    if addon.developer_comments:
        d['dev_comments'] = unicode(addon.developer_comments)

    if addon.takes_contributions:
        contribution = {
            'link': url(addon.contribution_url, src=src),
            'meet_developers': url(addon.meet_the_dev_url(), src=src),
            'suggested_amount': addon.suggested_amount,
        }
        d['contribution'] = contribution

    if addon.type == amo.ADDON_PERSONA:
        d['previews'] = [addon.persona.preview_url]
    elif addon.type == amo.ADDON_WEBAPP:
        d['app_type'] = addon.app_type_id
    else:
        d['previews'] = [p.as_dict(src=src) for p in addon.all_previews]

    return d
