from django.db import models
from django.utils import timezone


class Reindexing(models.Model):
    """Used to flag when an elasticsearch reindexing is occuring."""
    start_date = models.DateTimeField(default=timezone.now)
    alias = models.CharField(max_length=255)
    old_index = models.CharField(max_length=255, null=True)
    new_index = models.CharField(max_length=255)

    class Meta:
        db_table = 'zadmin_reindexing'

    @classmethod
    def is_reindexing(cls):
        """Return True if a reindexing is occuring for the given site."""
        return cls.objects.exists()

    @classmethod
    def flag_reindexing(cls, alias, old_index, new_index):
        """Mark down that we are reindexing."""
        if cls.is_reindexing():
            return  # Already flagged.

        return cls.objects.create(alias=alias, old_index=old_index,
                                  new_index=new_index)

    @classmethod
    def unflag_reindexing(cls, alias=None):
        """Mark down that we are done reindexing"""
        qs = cls.objects.all()
        if alias:
            qs = qs.filter(alias=alias)
        qs.delete()

    @classmethod
    def get_indices(cls, alias):
        """
        Return the indices associated with an alias.
        If we are reindexing, there should be two indices returned.
        """
        try:
            reindex = cls.objects.get(alias=alias)
            # Yes. Let's reindex on both indexes.
            return [idx for idx in reindex.new_index, reindex.old_index
                    if idx is not None]
        except Reindexing.DoesNotExist:
            return [alias]
