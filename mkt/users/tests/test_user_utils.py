from nose.tools import eq_

import mkt.site.tests
from mkt.access.models import Group
from mkt.api.models import Access
from mkt.users.utils import create_user


class TestCreateFakeUsers(mkt.site.tests.TestCase):
    def test_create_user(self):
        email = "faketestuser@example.com"
        key = "fake oauth key"
        secret = "fake oauth secret"
        Group.objects.create(name="Admins", rules="*:*")
        u = create_user(email, "Admins", oauth_key=key, oauth_secret=secret)
        eq_(u.email, email)
        eq_([g.name for g in u.groups.all()], ['Admins'])
        a = Access.objects.get(user=u)
        eq_(a.key, key)
        eq_(a.secret, secret)
