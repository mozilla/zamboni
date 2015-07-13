from functools import partial

from rest_framework import fields, serializers

import mkt
from mkt.access import acl
from mkt.api.serializers import PotatoCaptchaSerializer
from mkt.users.models import UserProfile


class AccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserProfile
        fields = ['display_name', 'enable_recommendations']

    def validate_display_name(self, attrs, source):
        """Validate that display_name is not empty"""
        value = attrs.get(source)
        if value is None or not value.strip():
            raise serializers.ValidationError("This field is required")
        return attrs

    def transform_display_name(self, obj, value):
        """Return obj.name instead of display_name to handle users without
        a valid display_name."""
        return obj.name


class AccountInfoSerializer(serializers.ModelSerializer):
    ALLOWED_SOURCES = [mkt.LOGIN_SOURCE_FXA]

    source = serializers.CharField(read_only=True)
    verified = serializers.BooleanField(source='is_verified', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['source', 'verified']

    def transform_source(self, obj, value):
        """Return the sources slug instead of the id."""
        if obj.pk is None:
            return mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_UNKNOWN]
        elif obj.source in self.ALLOWED_SOURCES:
            return mkt.LOGIN_SOURCE_LOOKUP[value]
        else:
            return mkt.LOGIN_SOURCE_LOOKUP[mkt.LOGIN_SOURCE_BROWSERID]


class FeedbackSerializer(PotatoCaptchaSerializer):
    feedback = fields.CharField()
    platform = fields.CharField(required=False)
    chromeless = fields.CharField(required=False)
    from_url = fields.CharField(required=False)
    user = fields.Field()

    def validate(self, attrs):
        attrs = super(FeedbackSerializer, self).validate(attrs)

        if not attrs.get('platform'):
            attrs['platform'] = self.request.GET.get('dev', '')
        if self.request.user.is_authenticated():
            attrs['user'] = self.request.user
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

    def transform_newsletter(self, obj, value):
        # Transform from the string the API receives to the one we need to pass
        # to basket.
        default = self.fields['newsletter'].default
        return self.NEWSLETTER_CHOICES_API.get(value, default)


class PermissionsSerializer(serializers.Serializer):
    permissions = fields.SerializerMethodField('get_permissions')

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
