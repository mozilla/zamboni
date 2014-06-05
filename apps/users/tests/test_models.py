# -*- coding: utf-8 -*-
import datetime

from django import forms
from django.conf import settings
from django.utils import translation

from mock import patch
from nose.tools import eq_

import amo
import amo.tests
from addons.models import Addon, AddonUser
from mkt.access.models import Group, GroupUser
from reviews.models import Review
from translations.models import Translation
from users.models import UserEmailField, UserProfile


class TestUserProfile(amo.tests.TestCase):
    fixtures = ('base/addon_3615', 'base/user_2519', 'base/user_4043307',
                'users/test_backends', 'base/apps',)

    def test_anonymize(self):
        u = UserProfile.objects.get(id='4043307')
        eq_(u.email, 'jbalogh@mozilla.com')
        u.anonymize()
        x = UserProfile.objects.get(id='4043307')
        eq_(x.email, None)

    def test_add_admin_powers(self):
        Group.objects.create(name='Admins', rules='*:*')
        u = UserProfile.objects.get(username='jbalogh')

        assert not u.is_staff
        assert not u.is_superuser
        GroupUser.objects.create(group=Group.objects.filter(name='Admins')[0],
                                 user=u)
        assert u.is_staff
        assert u.is_superuser

    def test_dont_add_admin_powers(self):
        Group.objects.create(name='API', rules='API.Users:*')
        u = UserProfile.objects.get(username='jbalogh')

        GroupUser.objects.create(group=Group.objects.get(name='API'),
                                 user=u)
        assert not u.is_staff
        assert not u.is_superuser

    def test_remove_admin_powers(self):
        Group.objects.create(name='Admins', rules='*:*')
        u = UserProfile.objects.get(username='jbalogh')
        g = GroupUser.objects.create(group=Group.objects.filter(name='Admins')[0],
                                     user=u)
        g.delete()
        assert not u.is_staff
        assert not u.is_superuser

    def test_picture_url(self):
        """
        Test for a preview URL if image is set, or default image otherwise.
        """
        u = UserProfile(id=1234, picture_type='image/png',
                        modified=datetime.date.today())
        u.picture_url.index('/userpics/0/1/1234.png?modified=')

        u = UserProfile(id=1234567890, picture_type='image/png',
                        modified=datetime.date.today())
        u.picture_url.index('/userpics/1234/1234567/1234567890.png?modified=')

        u = UserProfile(id=1234, picture_type=None)
        assert u.picture_url.endswith('/anon_user.png')

    def test_review_replies(self):
        """
        Make sure that developer replies are not returned as if they were
        original reviews.
        """
        addon = Addon.objects.get(id=3615)
        u = UserProfile.objects.get(pk=2519)
        version = addon.get_version()
        new_review = Review(version=version, user=u, rating=2, body='hello',
                            addon=addon)
        new_review.save()
        new_reply = Review(version=version, user=u, reply_to=new_review,
                           addon=addon, body='my reply')
        new_reply.save()

        review_list = [r.pk for r in u.reviews]

        eq_(len(review_list), 1)
        assert new_review.pk in review_list, (
            'Original review must show up in review list.')
        assert new_reply.pk not in review_list, (
            'Developer reply must not show up in review list.')

    def test_my_apps(self):
        """Test helper method to get N apps."""
        addon1 = Addon.objects.create(name='test-1', type=amo.ADDON_WEBAPP)
        AddonUser.objects.create(addon_id=addon1.id, user_id=2519, listed=True)
        addon2 = Addon.objects.create(name='test-2', type=amo.ADDON_WEBAPP)
        AddonUser.objects.create(addon_id=addon2.id, user_id=2519, listed=True)
        u = UserProfile.objects.get(id=2519)
        addons = u.my_apps()
        self.assertTrue(sorted([a.name for a in addons]) == [addon1.name,
                                                             addon2.name])

    def test_get_url_path(self):
        eq_(UserProfile(username='yolo').get_url_path(),
            '/en-US/firefox/user/yolo/')
        eq_(UserProfile(username='yolo', id=1).get_url_path(),
            '/en-US/firefox/user/yolo/')
        eq_(UserProfile(id=1).get_url_path(),
            '/en-US/firefox/user/1/')
        eq_(UserProfile(username='<yolo>', id=1).get_url_path(),
            '/en-US/firefox/user/1/')

    @patch.object(settings, 'LANGUAGE_CODE', 'en-US')
    def test_activate_locale(self):
        eq_(translation.get_language(), 'en-us')
        with UserProfile(username='yolo').activate_lang():
            eq_(translation.get_language(), 'en-us')

        with UserProfile(username='yolo', lang='fr').activate_lang():
            eq_(translation.get_language(), 'fr')

    def test_remove_locale(self):
        u = UserProfile.objects.create()
        u.bio = {'en-US': 'my bio', 'fr': 'ma bio'}
        u.save()
        u.remove_locale('fr')
        qs = (Translation.objects.filter(localized_string__isnull=False)
              .values_list('locale', flat=True))
        eq_(sorted(qs.filter(id=u.bio_id)), ['en-US'])


class TestUserEmailField(amo.tests.TestCase):
    fixtures = ['base/user_2519']

    def test_success(self):
        user = UserProfile.objects.get(pk=2519)
        eq_(UserEmailField().clean(user.email), user)

    def test_failure(self):
        with self.assertRaises(forms.ValidationError):
            UserEmailField().clean('xxx')

    def test_empty_email(self):
        UserProfile.objects.create(email='')
        with self.assertRaises(forms.ValidationError) as e:
            UserEmailField().clean('')
        eq_(e.exception.messages[0], 'This field is required.')
