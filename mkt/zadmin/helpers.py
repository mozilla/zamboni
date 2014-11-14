from django.template import defaultfilters

from jingo import register


# Only used in admin/settings.html
register.filter(defaultfilters.slugify)
