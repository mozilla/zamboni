from django.db import models
from django.core.urlresolvers import NoReverseMatch, reverse

import mkt
from mkt.site.models import ManagerBase, ModelBase
from mkt.site.utils import sorted_groupby


class TagManager(ManagerBase):

    def not_blocked(self):
        """Get allowed tags only"""
        return self.filter(blocked=False)


class Tag(ModelBase):
    tag_text = models.CharField(max_length=128)
    blocked = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)

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
        mkt.log(mkt.LOG.ADD_TAG, tag, addon)
        return tag

    def remove_tag(self, addon):
        tag, created = Tag.objects.get_or_create(tag_text=self.tag_text)
        for addon_tag in AddonTag.objects.filter(addon=addon, tag=tag):
            addon_tag.delete()
        mkt.log(mkt.LOG.REMOVE_TAG, tag, addon)


class AddonTag(ModelBase):
    addon = models.ForeignKey('webapps.Webapp', related_name='addon_tags')
    tag = models.ForeignKey(Tag, related_name='addon_tags')

    class Meta:
        db_table = 'users_tags_addons'


def attach_tags(objs, m2m_name):
    """
    Fetch tags from `objs` in one query and then attach them to a property on
    each instance. The name of the property will be `m2m_name` + '_list'.

    Assumes every instance in `objs` uses the same model, and needs `m2m_name`
    to be set to the name of the m2m field between the model and Tag.
    """
    if objs:
        obj_dict = {obj.id: obj for obj in objs}
        field_name = getattr(objs[0], m2m_name).query_field_name
        qs = (Tag.objects.not_blocked()
              .filter(**{'%s__in' % field_name: obj_dict.keys()})
              .values_list('%s__id' % field_name, 'tag_text'))
        for obj, tags in sorted_groupby(qs, lambda x: x[0]):
            setattr(obj_dict[obj], '%s_list' % m2m_name, [t[1] for t in tags])
