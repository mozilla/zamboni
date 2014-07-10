class DynamicBoolFieldsMixin(object):

    def _fields(self):
        """Returns array of all field names starting with 'has'."""
        return [f.name for f in self._meta.fields if f.name.startswith('has')]

    def to_dict(self):
        return dict((f, getattr(self, f)) for f in self._fields())

    def to_keys(self):
        return [k for k, v in self.to_dict().iteritems() if v]
