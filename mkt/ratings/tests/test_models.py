from django.utils import translation

from nose.tools import eq_
import test_utils

import amo.tests
from reviews.models import check_spam, Review, Spam


class TestReviewModel(amo.tests.TestCase):
    fixtures = ['base/apps', 'base/platforms', 'reviews/test_models']

    def test_translations(self):
        translation.activate('en-US')

        # There's en-US and de translations.  We should get en-US.
        r1 = Review.objects.get(id=1)
        test_utils.trans_eq(r1.title, 'r1 title en', 'en-US')

        # There's only a de translation, so we get that.
        r2 = Review.objects.get(id=2)
        test_utils.trans_eq(r2.title, 'r2 title de', 'de')

        translation.activate('de')

        # en and de exist, we get de.
        r1 = Review.objects.get(id=1)
        test_utils.trans_eq(r1.title, 'r1 title de', 'de')

        # There's only a de translation, so we get that.
        r2 = Review.objects.get(id=2)
        test_utils.trans_eq(r2.title, 'r2 title de', 'de')


class TestSpamTest(amo.tests.TestCase):
    fixtures = ['base/apps', 'base/platforms', 'reviews/test_models']

    def test_create_not_there(self):
        Review.objects.all().delete()
        eq_(Review.objects.count(), 0)
        check_spam(1)

    def test_add(self):
        assert Spam().add(Review.objects.all()[0], 'numbers')
