from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage
from django.utils import translation

import mock
from nose.tools import eq_

import mkt.users.notifications
from mkt.site.fixtures import fixture
from mkt.site.mail import send_mail, send_html_mail_jinja, _real_email_regexes
from mkt.site.models import FakeEmail
from mkt.site.tests import TestCase
from mkt.users.models import UserNotification, UserProfile
from mkt.zadmin.models import set_config


class TestSendMail(TestCase):
    fixtures = fixture('user_999', 'user_2519', 'user_10482')

    def setUp(self):
        self._email_blocked = list(getattr(settings, 'EMAIL_BLOCKED', []))

    def tearDown(self):
        translation.activate('en_US')
        settings.EMAIL_BLOCKED = self._email_blocked

    def test_send_string(self):
        to = 'f@f.com'
        with self.assertRaises(ValueError):
            send_mail('subj', 'body', recipient_list=to)

    def test_blocked(self):
        to = 'nobody@mozilla.org'
        to2 = 'somebody@mozilla.org'
        settings.EMAIL_BLOCKED = (to,)
        success = send_mail('test subject', 'test body',
                            recipient_list=[to, to2], fail_silently=False)
        assert success
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [to2])

    def test_blocked_flag(self):
        to = 'nobody@mozilla.org'
        to2 = 'somebody@mozilla.org'
        settings.EMAIL_BLOCKED = (to,)
        success = send_mail('test subject', 'test body',
                            recipient_list=[to, to2], fail_silently=False,
                            use_blocked=True)
        assert success
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [to2])

    def test_blocked_flag_off(self):
        to = 'nobody@mozilla.org'
        to2 = 'somebody@mozilla.org'
        settings.EMAIL_BLOCKED = (to,)
        success = send_mail('test subject', 'test_blocked_flag_off',
                            recipient_list=[to, to2], fail_silently=False,
                            use_blocked=False)
        assert success
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [to, to2])
        assert 'test_blocked_flag_off' in mail.outbox[0].body

    @mock.patch.object(settings, 'SEND_REAL_EMAIL', False)
    def test_real_regex_list(self):
        to = 'nooobody@mozilla.org'
        to2 = 'somebody@mozilla.org'
        to3 = 'reallywantsemail@mozilla.org'
        to4 = 'reallywantsemail+testing@mozilla.org'
        set_config('real_email_allowed_regex',
                   'reallywantsemail(\+[^@]+)?@mozilla.org')
        success = send_mail('test subject', 'test_real_list',
                            recipient_list=[to, to2, to3, to4],
                            fail_silently=False)
        assert success
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].to, [to3, to4])
        assert 'test_real_list' in mail.outbox[0].body
        eq_(FakeEmail.objects.count(), 1)  # Only one mail, two recipients.
        fake_email = FakeEmail.objects.get()
        eq_(fake_email.message.endswith('test_real_list'), True)
        assert ('To: %s, %s' % (to, to2)) in fake_email.message

    @mock.patch.object(settings, 'SEND_REAL_EMAIL', False)
    def test_bad_regexes(self):
        set_config('real_email_allowed_regex',
                   'reallywantsemail(\+[^@]+)?@mozilla.org,bad(regex{3')
        email_regexes = _real_email_regexes()
        eq_(len(email_regexes), 1)
        eq_(email_regexes[0].pattern, 'reallywantsemail(\+[^@]+)?@mozilla.org')

    def test_user_setting_default(self):
        user = UserProfile.objects.all()[0]
        to = user.email

        # Confirm there's nothing in the DB and we're using the default
        eq_(UserNotification.objects.count(), 0)

        # Make sure that this is True by default
        setting = mkt.users.notifications.NOTIFICATIONS_BY_SHORT['reply']
        eq_(setting.default_checked, True)

        success = send_mail('test subject', 'test body', perm_setting='reply',
                            recipient_list=[to], fail_silently=False)

        assert success, "Email wasn't sent"
        eq_(len(mail.outbox), 1)

    def test_user_setting_checked(self):
        user = UserProfile.objects.all()[0]
        to = user.email
        n = mkt.users.notifications.NOTIFICATIONS_BY_SHORT['reply']
        UserNotification.objects.get_or_create(notification_id=n.id,
                                               user=user, enabled=True)

        # Confirm we're reading from the database
        eq_(UserNotification.objects.filter(notification_id=n.id).count(), 1)

        success = send_mail('test subject', 'test body', perm_setting='reply',
                            recipient_list=[to], fail_silently=False)

        assert success, "Email wasn't sent"
        eq_(len(mail.outbox), 1)

    def test_user_mandatory(self):
        user = UserProfile.objects.all()[0]
        to = user.email
        n = mkt.users.notifications.NOTIFICATIONS_BY_SHORT[
            'individual_contact']

        UserNotification.objects.get_or_create(notification_id=n.id,
                                               user=user, enabled=True)

        assert n.mandatory, "Notification isn't mandatory"

        success = send_mail('test subject', 'test body', perm_setting=n,
                            recipient_list=[to], fail_silently=False)

        assert success, "Email wasn't sent"
        eq_(len(mail.outbox), 1)

    def test_user_setting_unchecked(self):
        user = UserProfile.objects.all()[0]
        to = user.email
        n = mkt.users.notifications.NOTIFICATIONS_BY_SHORT['reply']
        UserNotification.objects.get_or_create(notification_id=n.id,
                                               user=user, enabled=False)

        # Confirm we're reading from the database.
        eq_(UserNotification.objects.filter(notification_id=n.id).count(), 1)

        success = send_mail('test subject', 'test body', perm_setting='reply',
                            recipient_list=[to], fail_silently=False)

        assert success, "Email wasn't sent"
        eq_(len(mail.outbox), 0)

    @mock.patch.object(settings, 'EMAIL_BLOCKED', ())
    def test_success_real_mail(self):
        assert send_mail('test subject', 'test body',
                         recipient_list=['nobody@mozilla.org'],
                         fail_silently=False)
        eq_(len(mail.outbox), 1)
        eq_(mail.outbox[0].subject.find('test subject'), 0)
        eq_(mail.outbox[0].body.find('test body'), 0)

    @mock.patch.object(settings, 'EMAIL_BLOCKED', ())
    @mock.patch.object(settings, 'SEND_REAL_EMAIL', False)
    def test_success_fake_mail(self):
        assert send_mail('test subject', 'test body',
                         recipient_list=['nobody@mozilla.org'],
                         fail_silently=False)
        eq_(len(mail.outbox), 0)
        eq_(FakeEmail.objects.count(), 1)
        eq_(FakeEmail.objects.get().message.endswith('test body'), True)

    def test_send_html_mail_jinja(self):
        emails = ['omg@org.yes']
        subject = u'Test'
        html_template = 'purchase/receipt.html'
        text_template = 'purchase/receipt.ltxt'
        send_html_mail_jinja(
            subject, html_template, text_template,
            context={}, recipient_list=emails,
            from_email=settings.NOBODY_EMAIL,
            use_blocked=False,
            perm_setting='individual_contact',
            headers={'Reply-To': settings.MKT_REVIEWERS_EMAIL})

        msg = mail.outbox[0]
        message = msg.message()

        eq_(msg.to, emails)
        eq_(msg.subject, subject)
        eq_(msg.from_email, settings.NOBODY_EMAIL)
        eq_(msg.extra_headers['Reply-To'], settings.MKT_REVIEWERS_EMAIL)

        eq_(message.is_multipart(), True)
        eq_(message.get_content_type(), 'multipart/alternative')
        eq_(message.get_default_type(), 'text/plain')

        payload = message.get_payload()
        eq_(payload[0].get_content_type(), 'text/plain')
        eq_(payload[1].get_content_type(), 'text/html')

        message1 = payload[0].as_string()
        message2 = payload[1].as_string()

        assert '<A HREF' not in message1, 'text-only email contained HTML!'
        assert '<A HREF' in message2, 'HTML email did not contain HTML!'

    def test_send_multilines_subjects(self):
        send_mail('test\nsubject', 'test body', from_email='a@example.com',
                  recipient_list=['b@example.com'])
        eq_('test subject', mail.outbox[0].subject, 'Subject not stripped')

    def make_backend_class(self, error_order):
        throw_error = iter(error_order)

        def make_backend(*args, **kwargs):
            if next(throw_error):
                class BrokenMessage(object):
                    def __init__(*args, **kwargs):
                        pass

                    def send(*args, **kwargs):
                        raise RuntimeError('uh oh')

                    def attach_alternative(*args, **kwargs):
                        pass
                backend = BrokenMessage()
            else:
                backend = EmailMessage(*args, **kwargs)
            return backend
        return make_backend

    @mock.patch('mkt.site.tasks.EmailMessage')
    def test_async_will_retry(self, backend):
        backend.side_effect = self.make_backend_class([True, True, False])
        with self.assertRaises(RuntimeError):
            send_mail('test subject',
                      'test body',
                      recipient_list=['somebody@mozilla.org'])
        send_mail('test subject',
                  'test body',
                  async=True,
                  recipient_list=['somebody@mozilla.org'])

    @mock.patch('mkt.site.tasks.EmailMessage')
    def test_async_will_stop_retrying(self, backend):
        backend.side_effect = self.make_backend_class([True, True])
        with self.assertRaises(RuntimeError):
            send_mail('test subject',
                      'test body',
                      async=True,
                      max_retries=1,
                      recipient_list=['somebody@mozilla.org'])
