# -*- coding: utf-8 -*-
from django import forms
from django.test.client import RequestFactory

from nose.tools import eq_

import mkt
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.tags.models import Tag
from mkt.tags.utils import clean_tags
from mkt.users.models import UserProfile


class TestCleanTags(TestCase):
    fixtures = fixture('user_2519')

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.user = UserProfile.objects.get(pk=2519)
        self.request.user = self.user
        self.request.groups = ()

    def test_slugify(self):
        self.assertSetEqual(clean_tags(self.request, 'green eggs and ham'),
                            ['green eggs and ham'])
        self.assertSetEqual(clean_tags(self.request, 'ONE fish, TWO fish'),
                            ['one fish', 'two fish'])
        self.assertSetEqual(clean_tags(self.request, 'ONE fish, TWO fish, ,,'),
                            ['one fish', 'two fish'])

    def test_slugify_unicode(self):
        self.assertSetEqual(clean_tags(self.request, u'Dr. Seüss'),
                            [u'dr seüss'])

    def test_min_length(self):
        mkt.MIN_TAG_LENGTH = 2
        with self.assertRaises(forms.ValidationError) as e:
            clean_tags(self.request, 'a, b, c')
        eq_(e.exception.message, 'All tags must be at least 2 characters.')

    def test_max_length(self):
        # The max length is defined on the Tag model at 128 characters.
        with self.assertRaises(forms.ValidationError) as e:
            clean_tags(self.request, 'x' * 129)
        eq_(e.exception.message, 'All tags must be 128 characters or less '
                                 'after invalid characters are removed.')

    def test_max_tags(self):
        mkt.MAX_TAGS = 3
        with self.assertRaises(forms.ValidationError) as e:
            clean_tags(self.request, 'one fish, two fish, red fish, blue fish')
        eq_(e.exception.message, 'You have 1 too many tags.')

    def test_restricted_tag(self):
        Tag.objects.create(tag_text='thing one', restricted=True)
        with self.assertRaises(forms.ValidationError) as e:
            clean_tags(self.request, 'thing one, thing two')
        eq_(e.exception.message,
            '"thing one" is a reserved tag and cannot be used.')

    def test_restricted_tag_with_privileges(self):
        self.request.groups = [self.grant_permission(self.user, 'Apps:Edit')]
        Tag.objects.create(tag_text='thing one', restricted=True)
        self.assertSetEqual(clean_tags(self.request, 'thing one, thing two'),
                            ['thing one', 'thing two'])

    def test_restricted_max_tags(self):
        """Test restricted tags don't count towards the max total."""
        mkt.MAX_TAGS = 3
        self.request.groups = [self.grant_permission(self.user, 'Apps:Edit')]
        Tag.objects.create(tag_text='lorax', restricted=True)
        self.assertSetEqual(
            clean_tags(self.request, 'one, two, three, lorax'),
            ['one', 'two', 'three', 'lorax'])

    def test_blocked(self):
        Tag.objects.create(tag_text='grinch', blocked=True)
        with self.assertRaises(forms.ValidationError) as e:
            clean_tags(self.request, 'grinch, lorax')
        eq_(e.exception.message, 'Invalid tag: grinch')
