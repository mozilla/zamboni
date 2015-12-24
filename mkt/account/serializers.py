from functools import partial

from rest_framework import fields, serializers

import mkt
from mkt.access import acl
from mkt.access.models import Group
from mkt.api.serializers import PotatoCaptchaSerializer
from mkt.users.models import UserProfile


class AccountSerializer(serializers.ModelSerializer):

    display_name = serializers.CharField(required=True)

    class Meta:
        model = UserProfile
        fields = ['display_name', 'enable_recommendations']

    def to_representation(self, instance):
        """Return obj.name instead of display_name to handle users without
        a valid display_name."""
        data = super(AccountSerializer, self).to_representation(instance)
        data["display_name"] = instance.name
        return data


class AccountInfoSerializer(serializers.ModelSerializer):
    ALLOWED_SOURCES = [mkt.LOGIN_SOURCE_FXA]

    source = serializers.CharField(read_only=True)
    verified = serializers.BooleanField(source='is_verified', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['source', 'verified']

    def to_representation(self, obj):
        """Return the sources slug instead of the id."""
        data = super(AccountInfoSerializer, self).to_representation(obj)
        if obj.pk is None:
            source = mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_UNKNOWN]
        elif obj.source in self.ALLOWED_SOURCES:
            source = mkt.LOGIN_SOURCE_LOOKUP[obj.source]
        else:
            source = mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_BROWSERID]

        data["source"] = source
        return data


class FeedbackSerializer(PotatoCaptchaSerializer):
    feedback = fields.CharField(allow_blank=False)
    chromeless = fields.CharField(required=False)
    from_url = fields.CharField(required=False)
    user = fields.ReadOnlyField(required=False)
    platform = fields.CharField(required=False, allow_null=True)

    def to_representation(self, attrs):
        attrs = super(FeedbackSerializer, self).to_representation(attrs)
        if not attrs.get('platform'):
            attrs['platform'] = self.request.GET.get('dev', '')
        if self.request.user.is_authenticated():
            attrs['user'] = unicode(self.request.user)
        else:
            attrs['user'] = None

        return attrs


class LoginSerializer(serializers.Serializer):
    assertion = fields.CharField(required=True)
    audience = fields.CharField(required=False)
    is_mobile = fields.BooleanField(required=False, default=False)


class FxALoginSerializer(serializers.Serializer):
    auth_response = fields.CharField(required=True)
    state = fields.CharField(required=True)


class NewsletterSerializer(serializers.Serializer):
    NEWSLETTER_CHOICES_API = {
        # string passed to the API : actual string passed to basket.
        'about:apps': 'mozilla-and-you,marketplace-desktop',
        'marketplace-firefoxos': 'marketplace',
        'marketplace-desktop': 'mozilla-and-you',
        'marketplace-android': 'mozilla-and-you'
    }
    email = fields.EmailField()
    newsletter = fields.ChoiceField(
        default='marketplace-firefoxos',
        required=False,
        choices=NEWSLETTER_CHOICES_API.items())
    lang = fields.CharField()

    def to_representation(self, obj):
        """Transform from the string the API receives to the one we need to
        pass to basket."""
        data = super(NewsletterSerializer, self).to_representation(obj)
        default = self.fields['newsletter'].default
        data['newsletter'] = self.NEWSLETTER_CHOICES_API.get(obj['newsletter'],
                                                             default)
        return data


class PermissionsSerializer(serializers.Serializer):
    permissions = fields.SerializerMethodField()

    def get_permissions(self, obj):
        request = self.context['request']
        allowed = partial(acl.action_allowed, request)
        permissions = {
            'admin': allowed('Admin', '%'),
            'developer': request.user.is_developer,
            'localizer': allowed('Localizers', '%'),
            'lookup': allowed('AccountLookup', '%'),
            'curator': (
                allowed('Collections', 'Curate') or
                allowed('Feed', 'Curate')
            ),
            'reviewer': allowed('Apps', 'Review'),
            'webpay': (allowed('Transaction', 'NotifyFailure') and
                       allowed('ProductIcon', 'Create')),
            'website_submitter': allowed('Websites', 'Submit'),
            'stats': allowed('Stats', 'View'),
            'revenue_stats': allowed('RevenueStats', 'View'),
            'content_tools_addon_review': allowed('ContentTools',
                                                  'AddonReview'),
        }
        return permissions


class UserSerializer(AccountSerializer):
    """
    A wacky serializer type that unserializes PK numbers and
    serializes user fields.
    """
    resource_uri = serializers.HyperlinkedRelatedField(
        view_name='account-settings', source='pk',
        read_only=True)

    class Meta:
        model = UserProfile
        fields = ('display_name', 'resource_uri')


class GroupsSerializer(serializers.ModelSerializer):

    class Meta:
        model = Group
        fields = ('id', 'name', 'restricted')
        read_only_fields = ('id', 'name', 'restricted')


class TOSSerializer(serializers.Serializer):
    has_signed = fields.SerializerMethodField()

    def get_has_signed(self, obj):
        return (self.context['request'].user.read_dev_agreement is not None)
