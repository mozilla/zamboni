import datetime

from django.core.urlresolvers import reverse

from nose.tools import eq_
from pyquery import PyQuery as pq

import mkt
import mkt.site.tests
from mkt.developers.models import ActivityLog
from mkt.site.fixtures import fixture
from mkt.site.tests import formset
from mkt.users.models import UserProfile
from mkt.webapps.models import AddonUser, Webapp


class TestOwnership(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999')

    def setUp(self):
        self.webapp = self.get_webapp()
        self.url = self.webapp.get_dev_url('owner')
        self.login('steamcube@mozilla.com')
        # Users are required to have read the dev agreement to become owners.
        UserProfile.objects.filter(id__in=[31337, 999]).update(
            read_dev_agreement=datetime.datetime.now())

    def formset(self, *args, **kw):
        return formset(*args, **kw)

    def get_webapp(self):
        return Webapp.objects.get(id=337141)


class TestEditAuthor(TestOwnership):

    def test_reorder_authors(self):
        """
        Re-ordering authors should not generate role changes in the
        ActivityLog.
        """
        # flip form-0-position
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u = dict(user='regular@mozilla.com', listed=True,
                 role=mkt.AUTHOR_ROLE_DEV, position=0)
        data = self.formset(f.initial, u, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.status_code, 302)
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u1 = f.initial
        u1['position'] = 1
        f = self.client.get(self.url).context['user_form'].initial_forms[1]
        u2 = f.initial
        data = self.formset(u1, u2)

        orig = ActivityLog.objects.all().count()
        r = self.client.post(self.url, data)
        self.assert3xx(r, self.url, 302)
        eq_(ActivityLog.objects.all().count(), orig)

    def test_success_add_user(self):
        q = (AddonUser.objects.filter(addon=self.webapp.id)
             .values_list('user', flat=True))
        eq_(list(q.all()), [31337])

        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u = dict(user='regular@mozilla.com', listed=True,
                 role=mkt.AUTHOR_ROLE_DEV, position=0)
        data = self.formset(f.initial, u, initial_count=1)
        r = self.client.post(self.url, data)
        self.assert3xx(r, self.url, 302)
        self.assertSetEqual(q.all(), [31337, 999])

    def test_success_edit_user(self):
        # Add an author b/c we can't edit anything about the current one.
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u = dict(user='regular@mozilla.com', listed=True,
                 role=mkt.AUTHOR_ROLE_DEV, position=1)
        data = self.formset(f.initial, u, initial_count=1)
        self.client.post(self.url, data)
        eq_(AddonUser.objects.get(addon=self.webapp.id, user=999).listed, True)

        # Edit the user we just added.
        user_form = self.client.get(self.url).context['user_form']
        one, two = user_form.initial_forms
        del two.initial['listed']
        empty = dict(user='', listed=True, role=5, position=0)
        data = self.formset(one.initial, two.initial, empty, initial_count=2)
        r = self.client.post(self.url, data)
        self.assert3xx(r, self.url, 302)
        eq_(AddonUser.objects.get(addon=self.webapp.id, user=999).listed,
            False)

    def test_add_user_twice(self):
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u = dict(user='regular@mozilla.com', listed=True,
                 role=mkt.AUTHOR_ROLE_DEV, position=1)
        data = self.formset(f.initial, u, u, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.status_code, 200)
        eq_(r.context['user_form'].non_form_errors(),
            ['A team member can only be listed once.'])

    def test_success_delete_user(self):
        # Add a new user so we have one to delete.
        data = self.formset(dict(user='regular@mozilla.com', listed=True,
                                 role=mkt.AUTHOR_ROLE_OWNER, position=1),
                            initial_count=0)
        self.client.post(self.url, data)

        one, two = self.client.get(self.url).context['user_form'].initial_forms
        one.initial['DELETE'] = True
        data = self.formset(one.initial, two.initial, initial_count=2)
        r = self.client.post(self.url, data)
        eq_(r.status_code, 302)
        eq_(AddonUser.objects.get(addon=self.webapp.id).user_id, 999)

    def test_delete_unsub_comm(self):
        """Test that removing owner will unsubscribe them from Comm threads."""
        thread = self.webapp.threads.create()
        user = UserProfile.objects.filter(email='steamcube@mozilla.com')[0]
        user.comm_thread_cc.create(thread=thread, user=user)

        # Add.
        data = self.formset(dict(user='regular@mozilla.com', listed=True,
                                 role=mkt.AUTHOR_ROLE_OWNER, position=1),
                            initial_count=0)
        self.client.post(self.url, data)
        # Delete.
        one, two = self.client.get(self.url).context['user_form'].initial_forms
        one.initial['DELETE'] = True
        data = self.formset(one.initial, two.initial, initial_count=2)
        self.client.post(self.url, data)

        eq_(user.comm_thread_cc.count(), 0)

    def test_delete_own_access(self):
        # Add a new user and then delete the first user.
        data = self.formset(dict(user='regular@mozilla.com', listed=True,
                                 role=mkt.AUTHOR_ROLE_OWNER, position=1),
                            initial_count=0)
        self.client.post(self.url, data)
        one, two = self.client.get(self.url).context['user_form'].initial_forms
        one.initial['DELETE'] = True
        data = self.formset(one.initial, two.initial, initial_count=2)
        r = self.client.post(self.url, data)

        # We should be redirected to our My submissions page since we have
        # now lost access to the current app by deleting our own access.
        self.assert3xx(r, reverse('mkt.developers.apps'), 302)

    def test_delete_own_access_unsub_comm(self):
        """Test that removing self will unsubscribe self from Comm threads."""
        thread = self.webapp.threads.create()
        user = UserProfile.objects.filter(email='steamcube@mozilla.com')[0]
        user.comm_thread_cc.create(thread=thread, user=user)

        data = self.formset(dict(user='regular@mozilla.com', listed=True,
                                 role=mkt.AUTHOR_ROLE_OWNER, position=1),
                            initial_count=0)
        self.client.post(self.url, data)
        one, two = self.client.get(self.url).context['user_form'].initial_forms
        one.initial['DELETE'] = True
        data = self.formset(one.initial, two.initial, initial_count=2)
        self.client.post(self.url, data)

        eq_(user.comm_thread_cc.count(), 0)

    def test_switch_owner(self):
        # See if we can transfer ownership in one POST.
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        f.initial['user'] = 'regular@mozilla.com'
        data = self.formset(f.initial, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.status_code, 302)
        eq_(AddonUser.objects.get(addon=self.webapp.id).user_id, 999)
        eq_(ActivityLog.objects.filter(
            action=mkt.LOG.ADD_USER_WITH_ROLE.id).count(), 1)
        eq_(ActivityLog.objects.filter(
            action=mkt.LOG.REMOVE_USER_WITH_ROLE.id).count(), 1)

    def test_only_owner_can_edit(self):
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        u = dict(user='regular@mozilla.com', listed=True,
                 role=mkt.AUTHOR_ROLE_DEV, position=0)
        data = self.formset(f.initial, u, initial_count=1)
        self.client.post(self.url, data)

        self.login('regular@mozilla.com')
        self.client.post(self.url, data, follow=True)

        # Try deleting the other AddonUser.
        one, two = self.client.get(self.url).context['user_form'].initial_forms
        one.initial['DELETE'] = True
        data = self.formset(one.initial, two.initial, initial_count=2)
        r = self.client.post(self.url, data, follow=True)
        eq_(r.status_code, 403)
        eq_(AddonUser.objects.filter(addon=self.webapp.id).count(), 2)

    def test_must_have_listed(self):
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        f.initial['listed'] = False
        data = self.formset(f.initial, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.context['user_form'].non_form_errors(),
            ['At least one team member must be listed.'])

    def test_must_have_owner(self):
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        f.initial['role'] = mkt.AUTHOR_ROLE_DEV
        data = self.formset(f.initial, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.context['user_form'].non_form_errors(),
            ['Must have at least one owner.'])

    def test_must_have_owner_delete(self):
        f = self.client.get(self.url).context['user_form'].initial_forms[0]
        f.initial['DELETE'] = True
        data = self.formset(f.initial, initial_count=1)
        r = self.client.post(self.url, data)
        eq_(r.context['user_form'].non_form_errors(),
            ['Must have at least one owner.'])

    def test_author_support_role(self):
        # Tests that the support role shows up.
        res = self.client.get(self.url)
        eq_(res.status_code, 200)
        doc = pq(res.content)
        role_str = doc('#id_form-0-role').text()
        assert 'Support' in role_str, ('Support not in roles. Contained: %s' %
                                       role_str)


class TestEditWebappAuthors(mkt.site.tests.TestCase):
    fixtures = fixture('webapp_337141', 'user_999', 'user_admin',
                       'user_admin_group', 'group_admin')

    def setUp(self):
        self.login('admin@mozilla.com')
        self.webapp = Webapp.objects.get(id=337141)
        self.url = self.webapp.get_dev_url('owner')

    def test_apps_context(self):
        r = self.client.get(self.url)
        assert 'license_form' not in r.context, 'Unexpected license form'
        assert 'policy_form' not in r.context, 'Unexpected policy form'
        doc = pq(r.content)
        eq_(doc('.edit-addon-nav ul').eq(0).find('a').eq(4).attr('href'),
            self.url)

    def test_success_add_owner(self):
        u = UserProfile.objects.get(id=999)
        u = dict(user=u.email, listed=True, role=mkt.AUTHOR_ROLE_OWNER,
                 position=0)
        r = self.client.post(self.url, formset(u, initial_count=0))
        self.assert3xx(r, self.url, 302)
        owners = (AddonUser.objects.filter(addon=self.webapp.id)
                  .values_list('user', flat=True))
        eq_(set(owners), set([31337, 999]))


class TestDeveloperRoleAccess(mkt.site.tests.TestCase):
    fixtures = fixture('user_999', 'webapp_337141')

    def setUp(self):
        self.login('regular@mozilla.com')
        self.webapp = Webapp.objects.get(pk=337141)
        self.webapp.update(premium_type=mkt.ADDON_PREMIUM)

        user = UserProfile.objects.get(email='regular@mozilla.com')
        AddonUser.objects.create(addon=self.webapp, user=user,
                                 role=mkt.AUTHOR_ROLE_DEV)

    def _check_it(self, url):
        res = self.client.get(url, follow=True)
        eq_(res.status_code, 200)
        # Weak sauce. But pq('body.no-edit') or
        # pq('body').hasClass('no-edit') doesn't work.
        assert 'no-edit' in res.content, ("%s is editable by a developer but "
                                          "shouldn't be" % url)
        res = self.client.post(url)
        eq_(res.status_code, 403)

    def test_urls(self):
        urls = ['owner']
        for url in urls:
            self._check_it(self.webapp.get_dev_url(url))

    def test_disable(self):
        res = self.client.get(self.webapp.get_dev_url('versions'))
        doc = pq(res.content)
        eq_(doc('#delete-addon').length, 0)
        eq_(doc('#disable-addon').length, 1)

    def test_enable(self):
        self.webapp.update(disabled_by_user=True)
        res = self.client.get(self.webapp.get_dev_url('versions'))
        doc = pq(res.content)
        eq_(doc('#delete-addon').length, 0)
        eq_(doc('#enable-addon').length, 1)
