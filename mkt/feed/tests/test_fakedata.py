from nose.tools import eq_

import mkt.site.tests

from mkt.feed.models import FeedItem
from mkt.feed.fakedata import app_item, brand, collection, shelf
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp


class TestFeedGeneration(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def test_brand(self):
        app = Webapp.objects.get(pk=337141)
        br = brand(layout='grid', type='hidden-gem',
                   apps=[app], region='br')
        eq_(br.layout, 'grid')
        eq_(br.type, 'hidden-gem')
        eq_(list(br.apps()), [app])
        eq_(FeedItem.objects.get(brand=br).region, 7)

    def test_collection(self):
        app = Webapp.objects.get(pk=337141)
        co = collection(apps=[app], slug='test-coll', color='amber',
                        name='Example Collection',
                        description='Test Desc', region='br')
        eq_(co.slug, 'test-coll')
        eq_(co.color, 'amber')
        eq_(co.name, 'Example Collection')
        eq_(co.description, 'Test Desc')
        eq_(list(co.apps()), [app])
        eq_(FeedItem.objects.get(collection=co).region, 7)

    def test_shelf(self):
        app = Webapp.objects.get(pk=337141)
        sh = shelf(apps=[app], slug='test-shelf', name='Example Shelf',
                   description='Test Desc', region='br')
        eq_(sh.slug, 'test-shelf')
        eq_(sh.name, 'Example Shelf')
        eq_(sh.description, 'Test Desc')
        eq_(list(sh.apps()), [app])
        eq_(FeedItem.objects.get(shelf=sh).region, 7)

    def test_app(self):
        app = Webapp.objects.get(pk=337141)
        a = app_item(app, type='quote', slug='test-quote',
                     color='amber',
                     pullquote_attribution='test attribution',
                     pullquote_rating=1,
                     pullquote_text='test quote')
        eq_(a.type, 'quote')
        eq_(a.color, 'amber')
        eq_(a.slug, 'test-quote')
        eq_(unicode(a.pullquote_attribution), u'test attribution')
        eq_(a.pullquote_rating, 1)
        eq_(unicode(a.pullquote_text), u'test quote')
        eq_(a.app, app)
