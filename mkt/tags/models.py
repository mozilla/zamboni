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

    @classmethod
    def _get_m2m_name(cls, obj):
        """Return the related field name of the m2n on Tag."""
        related_models = cls._meta.get_all_related_m2m_objects_with_model()
        field_map = {rm[0].model: rm[0].field.name for rm in related_models}
        return field_map.get(obj._meta.model)

    def save_tag(self, obj):
        tag, created = Tag.objects.get_or_create(tag_text=self.tag_text)
        getattr(obj, self._get_m2m_name(obj)).add(tag)
        mkt.log(mkt.LOG.ADD_TAG, self.tag_text, obj)
        return tag

    def remove_tag(self, obj):
        for tag in obj.tags.filter(tag_text=self.tag_text):
            getattr(obj, self._get_m2m_name(obj)).remove(tag)
        mkt.log(mkt.LOG.REMOVE_TAG, self.tag_text, obj)


def attach_tags(objs):
    """
    Fetch tags from `objs` in one query and then attach them to a property on
    each instance.

    Assumes every instance in `objs` uses the same model.
    """
    if objs:
        obj_dict = {obj.id: obj for obj in objs}
        m2m_name = Tag._get_m2m_name(objs[0])
        field_name = getattr(objs[0], m2m_name).query_field_name
        qs = (Tag.objects.not_blocked()
              .filter(**{'%s__in' % field_name: obj_dict.keys()})
              .values_list('%s__id' % field_name, 'tag_text'))
        for obj, tags in sorted_groupby(qs, lambda x: x[0]):
            setattr(obj_dict[obj], '%s_list' % m2m_name, [t[1] for t in tags])
