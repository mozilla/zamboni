from nose.tools import eq_

import amo.tests
from mkt.site.fixtures import fixture
from mkt.tags.models import AddonTag, Tag
from mkt.tags.tasks import clean_tag
from mkt.webapps.models import Webapp


class TestTagManager(amo.tests.TestCase):

    def test_not_blacklisted(self):
        """Make sure Tag Manager filters right for not blacklisted tags."""
        tag1 = Tag(tag_text='abc', blacklisted=False)
        tag1.save()
        tag2 = Tag(tag_text='swearword', blacklisted=True)
        tag2.save()

        eq_(Tag.objects.all().count(), 2)
        eq_(Tag.objects.not_blacklisted().count(), 1)
        eq_(Tag.objects.not_blacklisted()[0], tag1)


class TestManagement(amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'tags')

    def setUp(self):
        self.addon = Webapp.objects.get(pk=337141)
        self.another = amo.tests.app_factory()

    def test_clean_tags(self):
        start = Tag.objects.count()
        caps = Tag.objects.create(tag_text='Sun')
        space = Tag.objects.create(tag_text='  Sun')

        clean_tag(caps.pk)
        clean_tag(space.pk)
        eq_(Tag.objects.count(), start)
        # Just to check another run doesn't make more changes.
        clean_tag(space.pk)
        eq_(Tag.objects.count(), start)

    def test_clean_addons_tags(self):
        space = Tag.objects.create(tag_text='  Sun')
        start = self.addon.tags.count()

        AddonTag.objects.create(tag=space, addon=self.addon)
        AddonTag.objects.create(tag=space, addon=self.another)

        eq_(self.another.tags.count(), 1)
        eq_(self.addon.tags.count(), start + 1)

        for tag in Tag.objects.all():
            clean_tag(tag.pk)

        # There is '  Sun' and 'sun' on addon, one gets deleted.
        eq_(self.addon.tags.count(), start)
        # There is 'sun' on another, should not be deleted.
        eq_(self.another.tags.count(), 1)

    def test_clean_doesnt_delete(self):
        space = Tag.objects.create(tag_text=' Sun')
        start = self.addon.tags.count()

        AddonTag.objects.create(tag=space, addon=self.another)

        eq_(self.another.tags.count(), 1)
        for tag in Tag.objects.all():
            clean_tag(tag.pk)

        # The 'sun' doesn't get deleted.
        eq_(self.addon.tags.count(), start)
        # There is 'sun' on another, should not be deleted.
        eq_(self.another.tags.count(), 1)

    def test_clean_multiple(self):
        for tag in ['sun', 'beach', 'sky']:
            caps = tag.upper()
            space = '  %s' % tag
            other = '. %s!  ' % tag
            for garbage in [caps, space, other]:
                garbage = Tag.objects.create(tag_text=garbage)
                for addon in (self.addon, self.another):
                    AddonTag.objects.create(tag=garbage, addon=addon)

        for tag in Tag.objects.all():
            clean_tag(tag.pk)

        eq_(self.addon.tags.count(), 5)
        eq_(self.another.tags.count(), 3)

    def setup_blacklisted(self):
        self.new = Tag.objects.create(tag_text=' Sun', blacklisted=True)
        self.old = Tag.objects.get(tag_text='sun')

    def test_blacklisted(self):
        self.setup_blacklisted()
        clean_tag(self.old.pk)
        assert not Tag.objects.get(tag_text='sun').blacklisted
        clean_tag(self.new.pk)
        assert Tag.objects.get(tag_text='sun').blacklisted

    def test_blacklisted_inverted(self):
        self.setup_blacklisted()
        clean_tag(self.new.pk)
        assert Tag.objects.get(tag_text='sun').blacklisted
        clean_tag(self.old.pk)
        assert Tag.objects.get(tag_text='sun').blacklisted


class TestCount(amo.tests.TestCase):
    fixtures = fixture('webapp_337141', 'tags')

    def setUp(self):
        self.tag = Tag.objects.get(pk=2652)

    def test_count(self):
        self.tag.update_stat()
        eq_(self.tag.num_addons, 1)

    def test_blacklisted(self):
        self.tag.update(blacklisted=True, num_addons=0)
        AddonTag.objects.create(addon_id=337141, tag_id=self.tag.pk)
        eq_(self.tag.reload().num_addons, 0)

    def test_save_tag(self):
        app = amo.tests.app_factory()
        self.tag.save_tag(addon=app)
        eq_(self.tag.reload().num_addons, 2)

    def test_remove_tag(self):
        app = amo.tests.app_factory()
        self.tag.remove_tag(addon=app)
        eq_(self.tag.reload().num_addons, 0)

    def test_add_addontag(self):
        AddonTag.objects.create(addon_id=337141, tag_id=self.tag.pk)
        eq_(self.tag.reload().num_addons, 2)

    def test_delete_addontag(self):
        addontag = AddonTag.objects.all()[0]
        tag = addontag.tag
        tag.update_stat()
        eq_(tag.reload().num_addons, 1)
        addontag.delete()
        eq_(tag.reload().num_addons, 0)

    def test_delete_tag(self):
        pk = self.tag.pk
        self.tag.update_stat()
        self.tag.delete()
        eq_(Tag.objects.filter(pk=pk).count(), 0)
