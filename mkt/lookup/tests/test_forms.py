from nose.tools import eq_, ok_

import amo.tests
from mkt.lookup.forms import (APIStatusForm, APIFileStatusForm,
                              TransactionRefundForm, TransactionSearchForm)


class TestTransactionSearchForm(amo.tests.TestCase):

    def test_basic(self):
        """Test the form doesn't crap out."""
        self.check_valid({'q': 12345}, True)

    def test_str_number(self):
        self.check_valid({'q': '12345'})

    def check_valid(self, data, valid=True):
        form = TransactionSearchForm(data)
        eq_(form.is_valid(), valid)


class TestTransactionRefundForm(amo.tests.TestCase):

    def test_not_fake(self):
        with self.settings(BANGO_FAKE_REFUNDS=False):
            assert 'fake' not in TransactionRefundForm().fields.keys()

    def test_fake(self):
        with self.settings(BANGO_FAKE_REFUNDS=True):
            assert 'fake' in TransactionRefundForm().fields.keys()


class TestAPIStatusForm(amo.tests.TestCase):

    def test_statuses(self):
        for status in amo.STATUS_CHOICES.keys():
            valid = status not in [amo.STATUS_BLOCKED, amo.STATUS_DELETED]
            ok_(APIStatusForm({'status': amo.STATUS_CHOICES_API[status]})
                .is_valid() == valid)


class TestAPIFileStatusForm(amo.tests.TestCase):

    def test_statuses(self):
        for status in amo.STATUS_CHOICES.keys():
            valid = status not in [amo.STATUS_BLOCKED, amo.STATUS_DELETED,
                                   amo.STATUS_UNPUBLISHED]
            ok_(APIFileStatusForm({'status': amo.STATUS_CHOICES_API[status]})
                .is_valid() == valid)
