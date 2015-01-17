from cStringIO import StringIO
from nose.tools import eq_, ok_

from django.core.management import call_command
from django.core.management.base import CommandError

import mkt.site.tests
from mkt.constants.carriers import TELEFONICA, AMERICA_MOVIL
from mkt.constants.regions import BRA, FRA
from mkt.operators.models import OperatorPermission
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestCommand(mkt.site.tests.TestCase):
    fixtures = fixture('user_999')

    def setUp(self):
        self.user = UserProfile.objects.get(pk=999)
        self.email = self.user.email
        self.buff = StringIO()

    def tearDown(self):
        if not self.buff.closed:
            self.buff.close()

    def call(self, *args, **opts):
        call_command('operator_user', stdout=self.buff, *args, **opts)
        self.buff.seek(0)
        return self.buff

    def test_invalid_command(self):
        with self.assertRaises(CommandError):
            self.call('foo')

    def add(self, email, carrier, region):
        self.call('add', email, carrier, region)

    def test_add(self):
        eq_(OperatorPermission.objects.all().count(), 0)
        self.add(self.email, TELEFONICA.slug, BRA.slug)
        qs = OperatorPermission.objects.all()
        eq_(qs.count(), 1)
        eq_(qs[0].user, self.user)
        eq_(qs[0].carrier, TELEFONICA.id)
        eq_(qs[0].region, BRA.id)

    def test_add_dupe(self):
        self.add(self.email, TELEFONICA.slug, BRA.slug)
        with self.assertRaises(CommandError):
            self.add(self.email, TELEFONICA.slug, BRA.slug)

    def test_add_invalid_user(self):
        with self.assertRaises(CommandError):
            self.add('foo@bar.com', TELEFONICA.slug, BRA.slug)

    def test_add_invalid_carrier(self):
        with self.assertRaises(CommandError):
            self.add(self.email, 'foocarrier', BRA.slug)

    def test_add_invalid_region(self):
        with self.assertRaises(CommandError):
            self.add(self.email, TELEFONICA.slug, 'fooregion')

    def test_add_bad_args(self):
        with self.assertRaises(CommandError):
            self.call('add', self.email)
        with self.assertRaises(CommandError):
            self.call('add', self.email, TELEFONICA.slug, BRA.slug, 'foo')

    def remove(self, email, carrier=None, region=None, all=False):
        self.call('remove', email, carrier, region, remove_all=all)

    def test_remove(self):
        self.add(self.email, TELEFONICA.slug, BRA.slug)
        self.remove(self.email, TELEFONICA.slug, BRA.slug)
        eq_(OperatorPermission.objects.all().count(), 0)

    def test_remove_nonexistant(self):
        with self.assertRaises(CommandError):
            self.remove(self.email, TELEFONICA.slug, BRA.slug)

    def test_remove_invalid_user(self):
        with self.assertRaises(CommandError):
            self.remove('foo@bar.com', TELEFONICA.slug, BRA.slug)

    def test_remove_invalid_carrier(self):
        with self.assertRaises(CommandError):
            self.remove(self.email, 'foocarrier', BRA.slug)

    def test_remove_invalid_region(self):
        with self.assertRaises(CommandError):
            self.remove(self.email, TELEFONICA.slug, 'fooregion')

    def test_remove_bad_args(self):
        with self.assertRaises(CommandError):
            self.call('remove', self.email)
        with self.assertRaises(CommandError):
            self.call('remove', self.email, TELEFONICA.slug, BRA.slug, 'foo')

    def test_remove_all(self):
        self.add(self.email, TELEFONICA.slug, BRA.slug)
        self.add(self.email, AMERICA_MOVIL.slug, FRA.slug)
        self.remove(self.email, all=True)
        eq_(OperatorPermission.objects.all().count(), 0)

    def test_remove_all_nonexistant(self):
        with self.assertRaises(CommandError):
            self.remove(self.email, all=True)

    def test_remove_all_invalid_email(self):
        with self.assertRaises(CommandError):
            self.remove('foo@bar.com', all=True)

    def list(self, email):
        return self.call('list', email)

    def test_list(self):
        pairs = [
            [TELEFONICA.slug, BRA.slug],
            [AMERICA_MOVIL.slug, FRA.slug],
        ]
        for carrier, region in pairs:
            self.add(self.email, carrier, region)
        output = self.list(self.email).read()
        for carrier, region in pairs:
            ok_(output.find('%s/%s' % (region, carrier)) >= 0)

    def test_list_invalid_email(self):
        with self.assertRaises(CommandError):
            self.list('foo@bar.com')
