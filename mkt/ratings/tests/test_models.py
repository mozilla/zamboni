from mock import patch
from nose.tools import eq_

import mkt.site.tests
from mkt.ratings.models import check_spam, Review, Spam
from mkt.ratings.tasks import addon_review_aggregates
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile


class TestSpamTest(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141')

    def setUp(self):
        self.app = Webapp.objects.get(pk=337141)
        self.user = UserProfile.objects.get(pk=31337)
        Review.objects.create(addon=self.app, user=self.user, title="review 1",
                              rating=3)
        Review.objects.create(addon=self.app, user=self.user, title="review 2",
                              rating=2)

    def test_create_not_there(self):
        Review.objects.all().delete()
        eq_(Review.objects.count(), 0)
        check_spam(1)

    def test_add(self):
        assert Spam().add(Review.objects.all()[0], 'numbers')

    @patch('mkt.ratings.tasks.addon_review_aggregates.delay')
    def test_refresh_triggers_review_aggregates(self, addon_review_aggregates):
        addon_review_aggregates.reset_mock()
        review = Review.objects.latest('pk')
        review.refresh()
        assert addon_review_aggregates.called

    @patch('mkt.webapps.tasks.index_webapps.original_apply_async')
    def test_review_aggregates_triggers_reindex(self, index_webapps):
        index_webapps.reset_mock()
        addon_review_aggregates(self.app.pk)
        assert index_webapps.called

    def test_soft_delete(self):
        Review.objects.all()[0].delete()
        eq_(Review.objects.count(), 1)
        eq_(Review.with_deleted.count(), 2)
