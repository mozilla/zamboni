#!/usr/bin/env python
import os
import requests

api_url = 'https://marketplace.firefox.com/api/v1/apps/category/?lang=%s'

english_categories = {  # Stolen from fireplace's categories.js
    'games': 'Games',
    # 'books': 'Books',  # Commented because already present in .po files.
    'business': 'Business',
    'education': 'Education',
    'entertainment': 'Entertainment',
    'health-fitness': 'Health & Fitness',
    'lifestyle': 'Lifestyle',
    'maps-navigation': 'Maps & Navigation',
    'music': 'Music',
    'news-weather': 'News & Weather',
    'photo-video': 'Photo & Video',
    'productivity': 'Productivity',
    'reference': 'Reference',
    'shopping': 'Shopping',
    'social': 'Social',
    'sports': 'Sports',
    'travel': 'Travel',
    'utilities': 'Utilities'
}


def build_locale_dict(data):
    if 'objects' not in data:
        return None
    return dict(((d['slug'], d['name']) for d in data['objects']
                 if d['slug'] in english_categories))


def write_po(filename, locale_categories):
    with open(filename, 'a') as f:
        for slug, translation in locale_categories.items():
            f.write('\n')
            f.write('#: /mkt/search/forms.py\n')
            f.write('msgid "%s"\n' % english_categories[slug])
            f.write('msgstr "%s"\n' % locale_categories[slug].encode('utf-8'))


def main():
    if not os.getcwd().endswith('locale'):
        print 'Run me from the locale/ directory please.'
        return

    for locale in os.listdir('.'):
        if not os.path.isdir(locale) or locale == 'templates':
            # print "Skipping %s since it's not a locale directory" % locale
            continue

        fname = os.path.join(locale, 'LC_MESSAGES', 'messages.po')
        if not os.path.exists(fname):
            # print "Skipping %s since it doesn't contain a messages.po file"
            continue

        print "Requesting categories for locale %s from the API" % locale
        response = requests.get(api_url % locale)
        if not response.status_code == 200:
            print "Error while requesting API, aborting script."
            return

        locale_categories = build_locale_dict(response.json())
        if locale_categories is None:
            print "Error in API response, aborting script."
            return

        if locale_categories == english_categories:
            print "Skipping '%s' since API response is not translated" % locale
            continue

        print "Writing %d translations to %s" % (len(locale_categories), fname)
        write_po(fname, locale_categories)


if __name__ == '__main__':
    main()
