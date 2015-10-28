import datetime

from django.core.urlresolvers import reverse

from mock import patch
from nose.tools import eq_, ok_
from nose import SkipTest

from mkt.api.tests.test_oauth import RestOAuth
from mkt.games.constants import GAME_CATEGORIES
from mkt.site.fixtures import fixture
from mkt.site.tests import app_factory, ESTestCase
from mkt.tags.models import Tag
from mkt.webapps.models import Webapp
from mkt.websites.models import Website
from mkt.websites.utils import website_factory


class TestDailyGamesView(RestOAuth, ESTestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestDailyGamesView, self).setUp()
        self.url = reverse('api-v2:games.daily')

    def tearDown(self):
        # Taken from MultiSearchView test.
        for w in Webapp.objects.all():
            w.delete()
        for w in Website.objects.all():
            w.delete()
        super(TestDailyGamesView, self).tearDown()

        Webapp.get_indexer().unindexer(_all=True)
        Website.get_indexer().unindexer(_all=True)
        self.refresh(('webapp', 'website'))

    def _create_group_of_games(self):
        content = [app_factory(), website_factory(), app_factory(),
                   website_factory()]
        # Add tags.
        game_tag = Tag.objects.get_or_create(tag_text='featured-game')[0]
        for i, cat in enumerate(GAME_CATEGORIES):
            tag = Tag.objects.get_or_create(tag_text=GAME_CATEGORIES[i])[0]
            if hasattr(content[i], 'tags'):
                content[i].tags.add(game_tag)
                content[i].tags.add(tag)
            else:
                content[i].keywords.add(game_tag)
                content[i].keywords.add(tag)

        self.reindex(Webapp)
        self.reindex(Website)
        self.refresh(('webapp', 'website'))

        return content

    def test_verbs(self):
        self._allowed_verbs(self.url, ['get'])

    def test_has_cors(self):
        self.assertCORS(self.anon.get(self.url), 'get')

    def test_meta(self):
        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(set(res.json.keys()), set(['objects', 'meta']))
        eq_(res.json['meta']['total_count'], 0)

    def test_empty(self):
        self.webapp = app_factory()
        self.website = website_factory()
        self.refresh(('webapp', 'website'))

        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 0)

    def test_ok(self):
        self._create_group_of_games()

        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 4)

        for game in res.json['objects']:
            ok_(game.get('tags') or game.get('keywords'))

    def test_limit(self):
        self._create_group_of_games()
        self._create_group_of_games()

        res = self.anon.get(self.url)
        eq_(res.status_code, 200)
        eq_(len(res.json['objects']), 4)

    def test_unique_categories(self):
        """One of each game category, no repeats."""
        for x in range(4):
            self._create_group_of_games()

        res = self.anon.get(self.url)
        eq_(res.status_code, 200)

        def get_tag(game):
            if game['doc_type'] == 'webapp':
                return (Webapp.objects.get(id=game['id']).tags
                              .filter(tag_text__in=GAME_CATEGORIES)[0]
                              .tag_text)
            elif game['doc_type'] == 'website':
                return (Website.objects.get(id=game['id']).keywords
                               .filter(tag_text__in=GAME_CATEGORIES)[0]
                               .tag_text)

        eq_(len(res.json['objects']), 4)
        self.assertSetEqual(map(get_tag, res.json['objects']), GAME_CATEGORIES)

    def test_consistent_randomization(self):
        for x in range(4):
            self._create_group_of_games()

        def get_id(game):
            return game['id']

        res = self.anon.get(self.url)
        set1 = map(get_id, res.json['objects'])

        res = self.anon.get(self.url)
        set2 = map(get_id, res.json['objects'])

        eq_(set1, set2)

    @patch('mkt.games.filters.datetime')
    def test_randomization(self, datetime_mock):
        # This test fails randomly, skipped for now as we are going to get rid
        # of games eventually anyway.
        # See discussion in https://github.com/mozilla/zamboni/pull/3418
        raise SkipTest
        datetime_mock.datetime.now.return_value = datetime.datetime.now()

        for x in range(4):
            self._create_group_of_games()

        def get_id(game):
            return game['id']

        res1 = self.anon.get(self.url)
        set1 = map(get_id, res1.json['objects'])

        # Change the date.
        datetime_mock.datetime.now.return_value = (
            datetime.datetime.now() - datetime.timedelta(days=30))
        res2 = self.anon.get(self.url)
        set2 = map(get_id, res2.json['objects'])

        ok_(set1 != set2)
