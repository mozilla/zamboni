# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from os import path

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.core.validators import ValidationError
from django.test.client import RequestFactory

import mock
from nose.tools import assert_raises, eq_, raises

import mkt
from mkt.site.fixtures import fixture
from mkt.site.tests import TestCase
from mkt.site.utils import (cache_ns_key, clean_tags, escape_all, ImageCheck,
                            LocalFileStorage, resize_image, rm_local_tmp_dir,
                            slug_validator, slugify, walkfiles)
from mkt.tags.models import Tag
from mkt.users.models import UserProfile


def get_image_path(name):
    return path.join(settings.ROOT, 'mkt', 'site', 'tests', 'images', name)


class TestAnimatedImages(TestCase):

    def test_animated_images(self):
        img = ImageCheck(open(get_image_path('animated.png')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.png')))
        assert not img.is_animated()

        img = ImageCheck(open(get_image_path('animated.gif')))
        assert img.is_animated()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert not img.is_animated()

    def test_junk(self):
        img = ImageCheck(open(__file__, 'rb'))
        assert not img.is_image()
        img = ImageCheck(open(get_image_path('non-animated.gif')))
        assert img.is_image()


def test_walkfiles():
    basedir = tempfile.mkdtemp()
    subdir = tempfile.mkdtemp(dir=basedir)
    file1, file1path = tempfile.mkstemp(dir=basedir, suffix='_foo')
    file2, file2path = tempfile.mkstemp(dir=subdir, suffix='_foo')
    file3, file3path = tempfile.mkstemp(dir=subdir, suffix='_bar')

    eq_(sorted(walkfiles(basedir, suffix='_foo')),
        sorted([file1path, file2path]))
    eq_(sorted(walkfiles(basedir)), sorted([file1path, file3path, file2path]))


u = u'Ελληνικά'


def test_slug_validator():
    eq_(slug_validator(u.lower()), None)
    eq_(slug_validator('-'.join([u.lower(), u.lower()])), None)
    assert_raises(ValidationError, slug_validator, '234.add')
    assert_raises(ValidationError, slug_validator, 'a a a')
    assert_raises(ValidationError, slug_validator, 'tags/')


def test_slugify():
    x = '-'.join([u, u])
    y = ' - '.join([u, u])

    def check(x, y):
        eq_(slugify(x), y)
        slug_validator(slugify(x))
    s = [
        ('xx x  - "#$@ x', 'xx-x-x'),
        (u'Bän...g (bang)', u'bäng-bang'),
        (u, u.lower()),
        (x, x.lower()),
        (y, x.lower()),
        ('    a ', 'a'),
        ('tags/', 'tags'),
        ('holy_wars', 'holy_wars'),
        # I don't really care what slugify returns. Just don't crash.
        (u'x荿', u'x\u837f'),
        (u'ϧ΃蒬蓣', u'\u03e7\u84ac\u84e3'),
        (u'¿x', u'x'),
    ]
    for val, expected in s:
        yield check, val, expected


def test_resize_image():
    # src and dst shouldn't be the same.
    assert_raises(Exception, resize_image, 't', 't', 'z')


def test_resize_transparency():
    src = get_image_path('transparent.png')
    dest = tempfile.mkstemp(dir=settings.TMP_PATH)[1]
    expected = src.replace('.png', '-expected.png')
    try:
        resize_image(src, dest, (32, 32), remove_src=False, locally=True)
        with open(dest) as dfh:
            with open(expected) as efh:
                assert dfh.read() == efh.read()
    finally:
        if os.path.exists(dest):
            os.remove(dest)


class TestLocalFileStorage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.stor = LocalFileStorage()

    def tearDown(self):
        rm_local_tmp_dir(self.tmp)

    def test_read_write(self):
        fn = os.path.join(self.tmp, 'somefile.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write('stuff')
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_non_ascii_filename(self):
        fn = os.path.join(self.tmp, u'Ivan Krsti\u0107.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write('stuff')
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_non_ascii_content(self):
        fn = os.path.join(self.tmp, 'somefile.txt')
        with self.stor.open(fn, 'w') as fd:
            fd.write(u'Ivan Krsti\u0107.txt'.encode('utf8'))
        with self.stor.open(fn, 'r') as fd:
            eq_(fd.read().decode('utf8'), u'Ivan Krsti\u0107.txt')

    def test_make_file_dirs(self):
        dp = os.path.join(self.tmp, 'path', 'to')
        self.stor.open(os.path.join(dp, 'file.txt'), 'w').close()
        assert os.path.exists(self.stor.path(dp)), (
            'Directory not created: %r' % dp)

    def test_do_not_make_file_dirs_when_reading(self):
        fpath = os.path.join(self.tmp, 'file.txt')
        with open(fpath, 'w') as fp:
            fp.write('content')
        # Make sure this doesn't raise an exception.
        self.stor.open(fpath, 'r').close()

    def test_make_dirs_only_once(self):
        dp = os.path.join(self.tmp, 'path', 'to')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fd:
            fd.write('stuff')
        # Make sure it doesn't try to make the dir twice
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fd:
            fd.write('stuff')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'r') as fd:
            eq_(fd.read(), 'stuff')

    def test_delete_empty_dir(self):
        dp = os.path.join(self.tmp, 'path')
        os.mkdir(dp)
        self.stor.delete(dp)
        eq_(os.path.exists(dp), False)

    @raises(OSError)
    def test_cannot_delete_non_empty_dir(self):
        dp = os.path.join(self.tmp, 'path')
        with self.stor.open(os.path.join(dp, 'file.txt'), 'w') as fp:
            fp.write('stuff')
        self.stor.delete(dp)

    def test_delete_file(self):
        dp = os.path.join(self.tmp, 'path')
        fn = os.path.join(dp, 'file.txt')
        with self.stor.open(fn, 'w') as fp:
            fp.write('stuff')
        self.stor.delete(fn)
        eq_(os.path.exists(fn), False)
        eq_(os.path.exists(dp), True)


class TestCacheNamespaces(unittest.TestCase):

    def setUp(self):
        cache.clear()
        self.namespace = 'redis-is-dead'

    @mock.patch('mkt.site.utils.epoch')
    def test_no_preexisting_key(self, epoch_mock):
        epoch_mock.return_value = 123456
        eq_(cache_ns_key(self.namespace), '123456:ns:%s' % self.namespace)

    @mock.patch('mkt.site.utils.epoch')
    def test_no_preexisting_key_incr(self, epoch_mock):
        epoch_mock.return_value = 123456
        eq_(cache_ns_key(self.namespace, increment=True),
            '123456:ns:%s' % self.namespace)

    @mock.patch('mkt.site.utils.epoch')
    def test_key_incr(self, epoch_mock):
        epoch_mock.return_value = 123456
        cache_ns_key(self.namespace)  # Sets ns to 123456
        ns_key = cache_ns_key(self.namespace, increment=True)
        expected = '123457:ns:%s' % self.namespace
        eq_(ns_key, expected)
        eq_(cache_ns_key(self.namespace), expected)


class TestEscapeAll(unittest.TestCase):

    def test_basics(self):
        x = '-'.join([u, u])
        y = ' - '.join([u, u])

        tests = [
            ('<script>alert("BALL SO HARD")</script>',
             '&lt;script&gt;alert("BALL SO HARD")&lt;/script&gt;'),
            (u'Bän...g (bang)', u'Bän...g (bang)'),
            (u, u),
            (x, x),
            (y, y),
            (u'x荿', u'x\u837f'),
            (u'ϧ΃蒬蓣', u'\u03e7\u0383\u84ac\u84e3'),
            (u'¿x', u'¿x'),
        ]

        for val, expected in tests:
            eq_(escape_all(val), expected)

    def test_nested(self):
        value = '<script>alert("BALL SO HARD")</script>'
        expected = '&lt;script&gt;alert("BALL SO HARD")&lt;/script&gt;'

        test = {
            'string': value,
            'dict': {'x': value},
            'list': [value],
            'bool': True,
        }
        res = escape_all(test)

        eq_(res['string'], expected)
        eq_(res['dict'], {'x': expected})
        eq_(res['list'], [expected])
        eq_(res['bool'], True)

    def test_without_linkify(self):
        value = '<button>http://firefox.com</button>'
        expected = '&lt;button&gt;http://firefox.com&lt;/button&gt;'

        test = {
            'string': value,
            'dict': {'x': value},
            'list': [value],
            'bool': True,
        }
        res = escape_all(test, linkify=False)

        eq_(res['string'], expected)
        eq_(res['dict'], {'x': expected})
        eq_(res['list'], [expected])
        eq_(res['bool'], True)


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
