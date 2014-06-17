from django.db import models
from django.core.urlresolvers import NoReverseMatch

import amo.models
from amo.urlresolvers import reverse


class TagManager(amo.models.ManagerBase):

    def not_blacklisted(self):
        """Get allowed tags only"""
        return self.filter(blacklisted=False)


class Tag(amo.models.ModelBase):
    tag_text = models.CharField(max_length=128)
    blacklisted = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)
    addons = models.ManyToManyField('webapps.Addon', through='AddonTag',
                                    related_name='tags')

    objects = TagManager()

    class Meta:
        db_table = 'tags'
        ordering = ('tag_text',)

    def __unicode__(self):
        return self.tag_text

    def can_reverse(self):
        try:
            self.get_url_path()
            return True
        except NoReverseMatch:
            return False

    def get_url_path(self):
        return reverse('tags.detail', args=[self.tag_text])

    def save_tag(self, addon):
        tag, created = Tag.objects.get_or_create(tag_text=self.tag_text)
        AddonTag.objects.get_or_create(addon=addon, tag=tag)
        amo.log(amo.LOG.ADD_TAG, tag, addon)
        return tag

    def remove_tag(self, addon):
        tag, created = Tag.objects.get_or_create(tag_text=self.tag_text)
        for addon_tag in AddonTag.objects.filter(addon=addon, tag=tag):
            addon_tag.delete()
        amo.log(amo.LOG.REMOVE_TAG, tag, addon)


class AddonTag(amo.models.ModelBase):
    addon = models.ForeignKey('webapps.Addon', related_name='addon_tags')
    tag = models.ForeignKey(Tag, related_name='addon_tags')

    class Meta:
        db_table = 'users_tags_addons'
