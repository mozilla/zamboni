from rest_framework import serializers

import mkt
from mkt.api.fields import ReverseChoiceField
from mkt.features.serializers import AppFeaturesSerializer
from mkt.files.models import File
from mkt.versions.models import Version


class SimpleVersionSerializer(serializers.ModelSerializer):
    resource_uri = serializers.HyperlinkedIdentityField(
        view_name='version-detail')

    class Meta:
        model = Version
        fields = ('version', 'resource_uri')


class VersionSerializer(serializers.ModelSerializer):
    addon = serializers.HyperlinkedRelatedField(view_name='app-detail',
                                                read_only=True)

    class Meta:
        model = Version
        fields = ('id', 'addon', '_developer_name', 'releasenotes', 'version')
        depth = 0
        field_rename = {
            '_developer_name': 'developer_name',
            'releasenotes': 'release_notes',
            'addon': 'app'
        }

    def to_representation(self, obj):
        native = super(VersionSerializer, self).to_representation(obj)

        # Add non-field data to the response.
        native.update({
            'features':
            AppFeaturesSerializer().to_representation(obj.features),
            'is_current_version': obj.addon.current_version == obj,
            'releasenotes': (unicode(obj.releasenotes) if obj.releasenotes else
                             None),
        })

        # Remap fields to friendlier, more backwards-compatible names.
        for old, new in self.Meta.field_rename.items():
            native[new] = native[old]
            del native[old]

        return native


class FileStatusSerializer(serializers.ModelSerializer):
    status = ReverseChoiceField(choices_dict=mkt.STATUS_CHOICES_API,
                                required=True)

    class Meta:
        model = File
        fields = ('status',)
