from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

import mock
from nose.tools import assert_false

import mkt
import mkt.site.tests
from mkt.site.fixtures import fixture
from mkt.webapps.models import Webapp
from mkt.users.models import UserProfile

from .acl import (action_allowed, check_addon_ownership, check_ownership,
                  check_reviewer, match_rules)


class ACLTestCase(mkt.site.tests.TestCase):
    """Test basic ACL by going to a locked page."""

    def test_match_rules(self):
        """
        Unit tests for the match_rules method.
        """

        rules = (
            '*:*',
            'Admin:%',
            'Admin:*',
            'Admin:Foo',
            'Apps:Edit,Admin:*',
            'Apps:Edit,Localizer:*,Admin:*',
        )

        for rule in rules:
            assert match_rules(rule, 'Admin', '%'), '%s != Admin:%%' % rule

        rules = (
            'Stats:View',
            'Apps:Edit',
            'None:None',
        )

        for rule in rules:
            assert not match_rules(rule, 'Admin', '%'), (
                "%s == Admin:%% and shouldn't" % rule)

    def test_anonymous_user(self):
        # Fake request must not have .groups, just like an anonymous user.
        fake_request = HttpRequest()
        assert_false(action_allowed(fake_request, 'Admin', '%'))

    def test_admin_login_anon(self):
        # Login form for anonymous user on the admin page.
        url = '/reviewers/'
        r = self.client.get(url)
        self.assertLoginRedirects(r, url)


class TestHasPerm(mkt.site.tests.TestCase):
    fixtures = fixture('group_admin', 'user_999', 'user_admin',
                       'user_admin_group', 'webapp_337141')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)
        self.app = Webapp.objects.get(pk=337141)
        self.app.addonuser_set.create(user=self.user)

        self.request = mock.Mock()
        self.request.groups = ()
        self.request.user = self.user

    def login_admin(self):
        user = UserProfile.objects.get(email='admin@mozilla.com')
        self.login(user)
        return user

    def test_anonymous(self):
        self.request.user = AnonymousUser()
        self.client.logout()
        assert not check_addon_ownership(self.request, self.app)

    def test_admin(self):
        self.request.user = self.login_admin()
        self.request.groups = self.request.user.groups.all()
        assert check_addon_ownership(self.request, self.app)
        assert check_addon_ownership(self.request, self.app, admin=True)
        assert not check_addon_ownership(self.request, self.app, admin=False)

    def test_require_author(self):
        self.login(self.user)
        assert check_ownership(self.request, self.app, require_author=True)

    def test_require_author_when_admin(self):
        self.login(self.user)
        self.request.user = self.login_admin()
        self.request.groups = self.request.user.groups.all()
        assert check_ownership(self.request, self.app, require_author=False)

        assert not check_ownership(self.request, self.app,
                                   require_author=True)

    def test_disabled(self):
        self.login(self.user)
        self.app.update(status=mkt.STATUS_DISABLED)
        assert not check_addon_ownership(self.request, self.app)
        self.test_admin()

    def test_deleted(self):
        self.login(self.user)
        self.app.update(status=mkt.STATUS_DELETED)
        assert not check_addon_ownership(self.request, self.app)
        self.request.user = self.login_admin()
        self.request.groups = self.request.user.groups.all()
        assert not check_addon_ownership(self.request, self.app)

    def test_ignore_disabled(self):
        self.login(self.user)
        self.app.update(status=mkt.STATUS_DISABLED)
        assert check_addon_ownership(self.request, self.app,
                                     ignore_disabled=True)

    def test_owner(self):
        self.login(self.user)
        assert check_addon_ownership(self.request, self.app)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_DEV)
        assert not check_addon_ownership(self.request, self.app)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_VIEWER)
        assert not check_addon_ownership(self.request, self.app)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_SUPPORT)
        assert not check_addon_ownership(self.request, self.app)

    def test_dev(self):
        self.login(self.user)
        assert check_addon_ownership(self.request, self.app, dev=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_DEV)
        assert check_addon_ownership(self.request, self.app, dev=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_VIEWER)
        assert not check_addon_ownership(self.request, self.app, dev=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_SUPPORT)
        assert not check_addon_ownership(self.request, self.app, dev=True)

    def test_viewer(self):
        self.login(self.user)
        assert check_addon_ownership(self.request, self.app, viewer=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_DEV)
        assert check_addon_ownership(self.request, self.app, viewer=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_VIEWER)
        assert check_addon_ownership(self.request, self.app, viewer=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_SUPPORT)
        assert check_addon_ownership(self.request, self.app, viewer=True)

    def test_support(self):
        self.login(self.user)
        assert check_addon_ownership(self.request, self.app, viewer=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_DEV)
        assert not check_addon_ownership(self.request, self.app,
                                         support=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_VIEWER)
        assert not check_addon_ownership(self.request, self.app,
                                         support=True)

        self.app.addonuser_set.update(role=mkt.AUTHOR_ROLE_SUPPORT)
        assert check_addon_ownership(self.request, self.app, support=True)


class TestCheckReviewer(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)

    def test_no_perm(self):
        req = mkt.site.tests.req_factory_factory('noop', user=self.user)
        assert not check_reviewer(req)

    def test_perm_apps(self):
        self.grant_permission(self.user, 'Apps:Review')
        req = mkt.site.tests.req_factory_factory('noop', user=self.user)
        assert check_reviewer(req)
