from django.conf import settings
from django.utils import translation

import waffle
from cache_nuggets.lib import memoize


def static_url(request):
    return {'STATIC_URL': settings.STATIC_URL}


def i18n(request):
    return {'LANGUAGES': settings.LANGUAGES,
            'LANG': settings.LANGUAGE_URL_MAP.get(translation.get_language())
                    or translation.get_language(),
            'DIR': 'rtl' if translation.get_language_bidi() else 'ltr',
            }


@memoize('collect-timings')
def get_collect_timings():
    # The flag has to be enabled for everyone and then we'll use that
    # percentage in the pages.
    percent = 0
    try:
        flag = waffle.models.Flag.objects.get(name='collect-timings')
        if flag.everyone and flag.percent:
            percent = float(flag.percent) / 100.0
    except waffle.models.Flag.DoesNotExist:
        pass
    return percent
