from datetime import date, datetime

from rest_framework import serializers

from mkt.api.fields import (ESTranslationSerializerField,
                            TranslationSerializerField)


def es_to_datetime(value):
    """
    Returns a datetime given an Elasticsearch date/datetime field.
    """
    if not value or isinstance(value, (date, datetime)):
        return

    if len(value) == 26:
        try:
            return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%f')
        except (TypeError, ValueError):
            pass
    elif len(value) == 19:
        try:
            return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
        except (TypeError, ValueError):
            pass
    elif len(value) == 10:
        try:
            return datetime.strptime(value, '%Y-%m-%d')
        except (TypeError, ValueError):
            pass

    return value


class BaseESSerializer(serializers.ModelSerializer):
    """
    A base deserializer that handles ElasticSearch data for a specific model.

    When deserializing, an unbound instance of the model (as defined by
    fake_object) is populated with the ES data in order to work well with
    the parent model serializer (e.g., AppSerializer).

    """
    # In base classes add the field names we want converted to Python
    # date/datetime from the Elasticsearch date strings.
    datetime_fields = ()

    def __init__(self, *args, **kwargs):
        super(BaseESSerializer, self).__init__(*args, **kwargs)

        # Set all fields as read_only just in case.
        for field_name in self.fields:
            self.fields[field_name].read_only = True

        if getattr(self, 'context'):
            for field_name in self.fields:
                self.fields[field_name].context = self.context

    def get_fields(self):
        """
        Return all fields as normal, with one exception: replace every instance
        of TranslationSerializerField with ESTranslationSerializerField.
        """
        fields = super(BaseESSerializer, self).get_fields()
        for key, field in fields.items():
            if isinstance(field, TranslationSerializerField):
                fields[key] = ESTranslationSerializerField(source=field.source)
                fields[key].initialize(parent=self, field_name=key)
        return fields

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
            value = data.get(field_name)
            if field_name in self.datetime_fields:
                value = self.to_datetime(value)
            setattr(obj, field_name, value)
        return obj

    def _attach_translations(self, obj, data, field_names):
        """Deserialize ES translation fields."""
        for field_name in field_names:
            ESTranslationSerializerField.attach_translations(
                obj, data, field_name)
        return obj

    def to_datetime(self, value):
        return es_to_datetime(value)


class DynamicSearchSerializer(serializers.Serializer):
    def __init__(self, **kwargs):
        super(DynamicSearchSerializer, self).__init__(**kwargs)
        serializer_classes = self.context.get('serializer_classes', {})
        self.serializers = {k: v(context=self.context)
                            for k, v in serializer_classes.items()}

    def to_native(self, obj):
        """
        Dynamically serialize obj using serializers passed through the context,
        depending on the doc_type of the obj.
        """
        if hasattr(obj, '_meta'):
            doc_type = obj._meta['doc_type']
        else:
            # For aggregated queries (mkt.games.ESGameAggregationPaginator).
            doc_type = obj['_type']

        serializer = self.serializers.get(doc_type)
        if serializer is None:
            return super(DynamicSearchSerializer, self).to_native(obj)
        data = serializer.to_native(obj)
        data['doc_type'] = doc_type
        return data
