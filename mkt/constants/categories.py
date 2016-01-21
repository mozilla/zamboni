from tower import ugettext_lazy as _lazy


CATEGORY_CHOICES = (
    ('books-comics', _lazy(u'Books & Comics')),
    ('business', _lazy(u'Business')),
    ('education', _lazy(u'Education')),
    ('entertainment', _lazy(u'Entertainment')),
    ('food-drink', _lazy(u'Food & Drink')),
    ('kids', _lazy(u'Kids')),
    ('games', _lazy(u'Games')),
    ('health-fitness', _lazy(u'Health & Fitness')),
    ('humor', _lazy(u'Humor')),
    ('internet', _lazy(u'Internet')),
    ('lifestyle', _lazy(u'Lifestyle')),
    ('maps-navigation', _lazy(u'Maps & Navigation')),
    ('music', _lazy(u'Music')),
    ('news', _lazy(u'News')),
    ('personalization', _lazy(u'Personalization')),
    ('photo-video', _lazy(u'Photo & Video')),
    ('productivity', _lazy(u'Productivity')),
    ('reference', _lazy(u'Reference')),
    ('science-tech', _lazy(u'Science & Tech')),
    ('shopping', _lazy(u'Shopping')),
    ('social', _lazy(u'Social')),
    ('sports', _lazy(u'Sports')),
    ('travel', _lazy(u'Travel')),
    ('utilities', _lazy(u'Utilities')),
    ('weather', _lazy(u'Weather')),
)

CATEGORY_CHOICES_DICT = dict(CATEGORY_CHOICES)

TARAKO_CATEGORIES_MAPPING = {
    'tarako-tools': ['business', 'education', 'productivity',
                     'reference', 'utilities'],
    'tarako-games': ['games'],
    'tarako-lifestyle': ['books-comics', 'entertainment', 'health-fitness',
                         'lifestyle', 'maps-navigation', 'music', 'news',
                         'photo-video', 'shopping', 'social', 'sports',
                         'travel', 'weather'],
}

TARAKO_CATEGORY_CHOICES = (
    ('tarako-tools', _lazy(u'Tools')),
    ('tarako-games', _lazy(u'Games')),
    ('tarako-lifestyle', _lazy(u'Lifestyle')),
)

# Past categories that have been moved need to redirect to the new category.
CATEGORY_REDIRECTS = {
    'books': 'books-comics',
    'news-weather': 'news',
}
