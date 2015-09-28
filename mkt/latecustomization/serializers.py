from rest_framework import relations, serializers

import mkt.carriers
import mkt.regions
from mkt.api.fields import SlugChoiceField
from mkt.extensions.models import Extension
from mkt.extensions.serializers import ExtensionSerializer
from mkt.webapps.models import Webapp
from mkt.webapps.serializers import SimpleAppSerializer
from mkt.latecustomization.models import LateCustomizationItem


class LateCustomizationSerializer(serializers.ModelSerializer):

    type = serializers.ChoiceField(choices=(("webapp", "webapp"),
                                            ("extension", "extension")))
    app = relations.PrimaryKeyRelatedField(required=False,
                                           queryset=Webapp.objects)
    extension = relations.PrimaryKeyRelatedField(required=False,
                                                 queryset=Extension.objects)
    carrier = SlugChoiceField(required=True,
                              choices_dict=mkt.carriers.CARRIER_MAP)
    region = SlugChoiceField(required=True,
                             choices_dict=mkt.regions.REGION_LOOKUP)

    class Meta:
        model = LateCustomizationItem

    def to_representation(self, obj):
        if obj.app is None:
            e = ExtensionSerializer(context=self.context)
            data = e.to_representation(obj.extension)
            data['latecustomization_id'] = obj.pk
            data['latecustomization_type'] = 'extension'
        else:
            a = SimpleAppSerializer(context=self.context)
            data = a.to_representation(obj.app)
            data['latecustomization_id'] = obj.pk
            data['latecustomization_type'] = 'webapp'
        return data

    def create(self, data):
        del data['type']
        return serializers.ModelSerializer.create(self, data)
