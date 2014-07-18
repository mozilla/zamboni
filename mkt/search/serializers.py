from rest_framework import serializers

from mkt.api.fields import ESTranslationSerializerField


class BaseESSerializer(serializers.ModelSerializer):
    """
    A base deserializer that handles ElasticSearch data for a specific model.
    When deserializing, an unbound instance of the model (as defined by
    fake_object) is populated with the ES data in order to work well with
    the parent model serializer (e.g., AppSerializer).
    """
    def __init__(self, *args, **kwargs):
        super(BaseESSerializer, self).__init__(*args, **kwargs)

        # Set all fields as read_only just in case.
        for field_name in self.fields:
            self.fields[field_name].read_only = True

        if getattr(self, 'context'):
            for field_name in self.fields:
                self.fields[field_name].context = self.context

    @property
    def data(self):
        """
        Returns the serialized data on the serializer.
        """
        if self._data is None:
            if self.many:
                self._data = [self.to_native(item) for item in self.object]
            else:
                self._data = self.to_native(self.object)
        return self._data

    def field_to_native(self, obj, field_name):
        # DRF's field_to_native calls .all(), which we want to avoid, so we
        # provide a simplified version that doesn't and just iterates on the
        # object list.
        if hasattr(obj, 'object_list'):
            return [self.to_native(item) for item in obj.object_list]
        return super(BaseESSerializer, self).field_to_native(obj, field_name)

    def to_native(self, data):
        data = (data._source if hasattr(data, '_source') else
                data.get('_source', data))
        obj = self.fake_object(data)
        return super(BaseESSerializer, self).to_native(obj)

    def fake_object(self, data):
        """
        Create a fake instance from ES data which serializer fields will source
        from.
        """
        raise NotImplementedError

    def _attach_fields(self, obj, data, field_names):
        """Attach fields to fake instance."""
        for field_name in field_names:
            setattr(obj, field_name, data.get(field_name))
        return obj

    def _attach_translations(self, obj, data, field_names):
        """Deserialize ES translation fields."""
        for field_name in field_names:
            ESTranslationSerializerField.attach_translations(
                obj, data, field_name)
        return obj
