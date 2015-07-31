from mkt.fireplace.serializers import (FireplaceESAppSerializer,
                                       FireplaceESWebsiteSerializer)


class GamesESAppSerializer(FireplaceESAppSerializer):
    """Include tags."""
    class Meta(FireplaceESAppSerializer.Meta):
        fields = FireplaceESAppSerializer.Meta.fields + ['tags']
        exclude = FireplaceESAppSerializer.Meta.exclude


class GamesESWebsiteSerializer(FireplaceESWebsiteSerializer):
    """Include keywords."""
    class Meta(FireplaceESWebsiteSerializer.Meta):
        fields = FireplaceESWebsiteSerializer.Meta.fields + ['keywords']
