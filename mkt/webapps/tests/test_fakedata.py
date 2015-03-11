import collections

from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.webapps.fakedata import (fake_app_names, generate_app_data,
                                  generate_app_from_spec)


class TestAppGeneration(mkt.site.tests.TestCase):
    def test_tinyset(self):
        size = 4
        data = list(generate_app_data(size))
        eq_(len(data), size)
        ctr = collections.defaultdict(int)
        for appname, cat in data:
            ctr[cat] += 1
        # Apps are binned into categories, at least 3 in each.
        eq_(ctr.values(), [4])
        # Names are unique.
        eq_(len(set(appname for appname, cat in data)), size)
        # Size is smaller than name list, so no names end in numbers.
        ok_(not any(appname[-1].isdigit() for appname, cat in data))

    def test_smallset(self):
        size = 60
        data = list(generate_app_data(size))
        eq_(len(data), size)
        ctr = collections.defaultdict(int)
        for appname, cat in data:
            ctr[cat] += 1
        eq_(set(ctr.values()), set([3, 4]))
        eq_(len(set(appname for appname, cat in data)), size)
        ok_(not any(appname[-1].isdigit() for appname, cat in data))

    def test_bigset(self):
        size = 300
        data = list(generate_app_data(size))
        eq_(len(data), size)
        ctr = collections.defaultdict(int)
        for appname, cat in data:
            ctr[cat] += 1
        # Apps are spread between categories evenly - the difference between
        # the largest and smallest category is less than 2.
        ok_(max(ctr.values()) - min(ctr.values()) < 2)
        eq_(len(set(appname for appname, cat in data)), size)
        # Every name is used without a suffix.
        eq_(sum(1 for appname, cat in data if not appname[-1].isdigit()),
            len(fake_app_names))
        # Every name is used with ' 1' as a suffix.
        eq_(sum(1 for appname, cat in data if appname.endswith(' 1')),
            len(fake_app_names))

    def test_generate_hosted_app(self):
        appname = 'a test app'
        categories = ['books', 'music']
        app = generate_app_from_spec(
            appname, categories, 'hosted', num_previews=3,
            num_ratings=4, num_locales=1, status='public')
        eq_(app.name, appname)
        eq_(app.categories, categories)
        eq_(app.status, 4)
        eq_(app.reload().total_reviews, 4)
        eq_(app.reviews.count(), 4)
        eq_(app.get_previews().count(), 3)

    def test_generate_packaged_app(self):
        appname = 'a test app'
        categories = ['books', 'music']
        app = generate_app_from_spec(
            appname, categories, 'packaged', num_previews=3,
            num_ratings=4, num_locales=1, status='public',
            versions=['public', 'disabled', 'public'])
        eq_(app.name, appname)
        eq_(app.categories, categories)
        eq_(app.status, 4)
        eq_(app.reload().total_reviews, 4)
        eq_(app.reviews.count(), 4)
        eq_(app.get_previews().count(), 3)
        eq_(app.versions.count(), 3)
        eq_(app.latest_version.version, '1.2')

    def test_generate_privileged_app(self):
        appname = 'a test app'
        categories = ['books', 'music']
        app = generate_app_from_spec(
            appname, categories, 'privileged', num_previews=3,
            num_ratings=4, num_locales=1, status='public',
            permissions=['storage'], versions=['public', 'disabled', 'public'])
        eq_(app.name, appname)
        eq_(app.categories, categories)
        eq_(app.status, 4)
        eq_(app.reload().total_reviews, 4)
        eq_(app.reviews.count(), 4)
        eq_(app.get_previews().count(), 3)
        eq_(app.versions.count(), 3)
        eq_(app.latest_version.version, '1.2')
