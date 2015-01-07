import mkt.site.tests

from mkt.access.acl import action_allowed_user
from mkt.site.fixtures import fixture
from mkt.zadmin.management.commands.addusertogroup import do_adduser
from mkt.zadmin.management.commands.removeuserfromgroup import do_removeuser
from mkt.users.models import UserProfile


class TestCommand(mkt.site.tests.TestCase):
    fixtures = fixture('group_admin', 'user_10482')

    def test_group_management(self):
        x = UserProfile.objects.get(pk=10482)
        assert not action_allowed_user(x, 'Admin', '%')
        do_adduser('10482', '1')
        assert action_allowed_user(x, 'Admin', '%')
        do_removeuser('10482', '1')
        assert not action_allowed_user(x, 'Admin', '%')
