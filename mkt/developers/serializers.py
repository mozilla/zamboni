from rest_framework.serializers import ModelSerializer, SerializerMethodField

from mkt.webapps.models import ContentRating


class ContentRatingSerializer(ModelSerializer):
    body = SerializerMethodField()
    rating = SerializerMethodField()

    def get_body(self, obj):
        return obj.get_body().label

    def get_rating(self, obj):
        return obj.get_rating().label

    class Meta:
        model = ContentRating
        fields = ('created', 'modified', 'body', 'rating')
