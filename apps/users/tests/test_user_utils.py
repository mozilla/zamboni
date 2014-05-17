import fudge
import mock
from nose.tools import eq_

from django.conf import settings

import amo.tests
from users.utils import autocreate_username


class TestAutoCreateUsername(amo.tests.TestCase):

    def test_invalid_characters(self):
        eq_(autocreate_username('testaccount+slug'), 'testaccountslug')

    def test_empty_username_is_a_random_hash(self):
        un = autocreate_username('.+')  # this shouldn't happen but it could!
        assert len(un) and not un.startswith('.+'), 'Unexpected: %s' % un

    @mock.patch.object(settings, 'MAX_GEN_USERNAME_TRIES', 3)
    @fudge.patch('users.utils.UserProfile.objects.filter')
    def test_too_many_tries(self, filter):
        filter = (filter.is_callable().returns_fake().provides('count')
                  .returns(1))
        for i in range(3):
            # Simulate existing username.
            filter = filter.next_call().returns(1)
        # Simulate available username.
        filter = filter.next_call().returns(0)
        # After the third try, give up, and generate a random string username.
        un = autocreate_username('base')
        assert not un.startswith('base'), 'Unexpected: %s' % un

    @fudge.patch('users.utils.UserProfile.objects.filter')
    def test_duplicate_username_counter(self, filter):
        filter = (filter.expects_call().returns_fake().expects('count')
                  .returns(1).next_call().returns(1).next_call().returns(0))
        eq_(autocreate_username('existingname'), 'existingname3')
