from tower import ugettext_lazy as _lazy


CATEGORY_CHOICES = (
    ('books', _lazy(u'Books')),
    ('business', _lazy(u'Business')),
    ('education', _lazy(u'Education')),
    ('entertainment', _lazy(u'Entertainment')),
    ('games', _lazy(u'Games')),
    ('health-fitness', _lazy(u'Health & Fitness')),
    ('lifestyle', _lazy(u'Lifestyle')),
    ('maps-navigation', _lazy(u'Maps & Navigation')),
    ('music', _lazy(u'Music')),
    ('news-weather', _lazy(u'News & Weather')),
    ('photo-video', _lazy(u'Photo & Video')),
    ('productivity', _lazy(u'Productivity')),
    ('reference', _lazy(u'Reference')),
    ('shopping', _lazy(u'Shopping')),
    ('social', _lazy(u'Social')),
    ('sports', _lazy(u'Sports')),
    ('travel', _lazy(u'Travel')),
    ('utilities', _lazy(u'Utilities'))
)

CATEGORY_CHOICES_DICT = dict(CATEGORY_CHOICES)

TARAKO_CATEGORIES_MAPPING = {
    'tarako-tools': ['business', 'education', 'productivity',
                     'reference', 'utilities'],
    'tarako-games': ['games'],
    'tarako-lifestyle': ['books', 'entertainment', 'health-fitness',
                         'lifestyle', 'maps-navigation', 'music',
                         'news-weather', 'photo-video', 'shopping',
                         'social', 'sports', 'travel'],
}

TARAKO_CATEGORY_CHOICES = (
    ('tarako-tools', _lazy(u'Tools')),
    ('tarako-games', _lazy(u'Games')),
    ('tarako-lifestyle', _lazy(u'Lifestyle')),
)
