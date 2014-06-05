from rest_framework import serializers

from mkt.abuse.models import AbuseReport
from mkt.account.serializers import UserSerializer
from mkt.api.fields import SlugOrPrimaryKeyRelatedField, SplitField
from mkt.webapps.models import Webapp
from mkt.webapps.serializers import SimpleAppSerializer


class BaseAbuseSerializer(serializers.ModelSerializer):
    text = serializers.CharField(source='message')
    ip_address = serializers.CharField(required=False)
    reporter = SplitField(serializers.PrimaryKeyRelatedField(required=False),
                          UserSerializer())

    def save(self, force_insert=False):
        serializers.ModelSerializer.save(self)
        del self.data['ip_address']
        return self.object


class UserAbuseSerializer(BaseAbuseSerializer):
    user = SplitField(serializers.PrimaryKeyRelatedField(), UserSerializer())

    class Meta:
        model = AbuseReport
        fields = ('text', 'ip_address', 'reporter', 'user')


class AppAbuseSerializer(BaseAbuseSerializer):
    app = SplitField(
        SlugOrPrimaryKeyRelatedField(source='addon', slug_field='app_slug',
                                     queryset=Webapp.objects.all()),
        SimpleAppSerializer(source='addon'))

    class Meta:
        model = AbuseReport
        fields = ('text', 'ip_address', 'reporter', 'app')
