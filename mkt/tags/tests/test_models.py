from nose.tools import eq_, ok_

import mkt.site.tests
from mkt.site.utils import app_factory
from mkt.tags.models import attach_tags, Tag
from mkt.websites.utils import website_factory


class TestTagManager(mkt.site.tests.TestCase):

    def test_not_blocked(self):
        """Make sure Tag Manager filters right for not blocked tags."""
        tag1 = Tag(tag_text='abc', blocked=False)
        tag1.save()
        tag2 = Tag(tag_text='swearword', blocked=True)
        tag2.save()

        eq_(Tag.objects.all().count(), 2)
        eq_(Tag.objects.not_blocked().count(), 1)
        eq_(Tag.objects.not_blocked()[0], tag1)


class TestAttachTags(mkt.site.tests.TestCase):

    def test_attach_tags_apps(self):
        tag1 = Tag.objects.create(tag_text='abc', blocked=False)
        tag2 = Tag.objects.create(tag_text='xyz', blocked=False)
        tag3 = Tag.objects.create(tag_text='swearword', blocked=True)

        app1 = app_factory()
        app1.tags.add(tag1)
        app1.tags.add(tag2)
        app1.tags.add(tag3)

        app2 = app_factory()
        app2.tags.add(tag2)
        app2.tags.add(tag3)

        app3 = app_factory()

        ok_(not hasattr(app1, 'tags_list'))
        attach_tags([app3, app2, app1])
        eq_(app1.tags_list, ['abc', 'xyz'])
        eq_(app2.tags_list, ['xyz'])
        ok_(not hasattr(app3, 'tags_list'))

    def test_attach_tags_websites(self):
        tag1 = Tag.objects.create(tag_text='abc', blocked=False)
        tag2 = Tag.objects.create(tag_text='xyz', blocked=False)
        tag3 = Tag.objects.create(tag_text='swearword', blocked=True)

        website1 = website_factory()
        website1.keywords.add(tag1)
        website1.keywords.add(tag2)
        website1.keywords.add(tag3)

        website2 = website_factory()
        website2.keywords.add(tag2)
        website2.keywords.add(tag3)

        website3 = website_factory()

        ok_(not hasattr(website1, 'keywords_list'))
        attach_tags([website3, website2, website1])
        eq_(website1.keywords_list, ['abc', 'xyz'])
        eq_(website2.keywords_list, ['xyz'])
        ok_(not hasattr(website3, 'keywords_list'))
