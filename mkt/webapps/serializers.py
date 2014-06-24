import json
from decimal import Decimal

from django.core.urlresolvers import reverse

from rest_framework import response, serializers

import commonware.log
from tower import ungettext as ngettext

import amo
import mkt
from amo.utils import no_translation
from constants.payments import PROVIDER_BANGO
from mkt.api.fields import (LargeTextField, ReverseChoiceField,
                            SemiSerializerMethodField,
                            TranslationSerializerField)
from mkt.constants.features import FeatureProfile
from mkt.prices.models import AddonPremium, Price
from mkt.submit.forms import mark_for_rereview
from mkt.submit.serializers import PreviewSerializer, SimplePreviewSerializer
from mkt.webapps.models import (AddonCategory, AddonUpsell, AppFeatures,
                                Category, Webapp)


log = commonware.log.getLogger('z.api')


class AppFeaturesSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppFeatures

    def to_native(self, obj):
        ret = super(AppFeaturesSerializer, self).to_native(obj)
        profile = FeatureProfile.from_signature(obj.to_signature())
        ret['required'] = profile.to_list()
        return ret


def http_error(errorclass, reason, extra_data=None):
    r = errorclass()
    data = {'reason': reason}
    if extra_data:
        data.update(extra_data)
    r.content = json.dumps(data)
    return response.Response(r)


class RegionSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    mcc = serializers.CharField()
    adolescent = serializers.BooleanField()


class AppSerializer(serializers.ModelSerializer):
    app_type = serializers.ChoiceField(
        choices=amo.ADDON_WEBAPP_TYPES_LOOKUP.items(), read_only=True)
    author = serializers.CharField(source='developer_name', read_only=True)
    banner_message = TranslationSerializerField(read_only=True,
        source='geodata.banner_message')
    banner_regions = serializers.Field(source='geodata.banner_regions_slugs')
    categories = serializers.SlugRelatedField(source='categories',
        many=True, slug_field='slug', required=True,
        queryset=Category.objects.filter(type=amo.ADDON_WEBAPP))
    content_ratings = serializers.SerializerMethodField('get_content_ratings')
    created = serializers.DateField(read_only=True)
    current_version = serializers.CharField(source='current_version.version',
                                            read_only=True)
    default_locale = serializers.CharField(read_only=True)
    device_types = SemiSerializerMethodField('get_device_types')
    description = TranslationSerializerField(required=False)
    homepage = TranslationSerializerField(required=False)
    icons = serializers.SerializerMethodField('get_icons')
    id = serializers.IntegerField(source='pk', required=False)
    is_offline = serializers.BooleanField(read_only=True)
    is_packaged = serializers.BooleanField(read_only=True)
    manifest_url = serializers.CharField(source='get_manifest_url',
                                         read_only=True)
    name = TranslationSerializerField(required=False)
    package_path = serializers.CharField(source='get_package_path',
                                         read_only=True)
    payment_account = serializers.SerializerMethodField('get_payment_account')
    payment_required = serializers.SerializerMethodField(
        'get_payment_required')
    premium_type = ReverseChoiceField(
        choices_dict=amo.ADDON_PREMIUM_API, required=False)
    previews = PreviewSerializer(many=True, required=False,
                                 source='all_previews')
    price = SemiSerializerMethodField('get_price')
    price_locale = serializers.SerializerMethodField('get_price_locale')
    privacy_policy = LargeTextField(view_name='app-privacy-policy-detail',
                                    required=False)
    public_stats = serializers.BooleanField(read_only=True)
    ratings = serializers.SerializerMethodField('get_ratings_aggregates')
    regions = RegionSerializer(read_only=True, source='get_regions')
    release_notes = TranslationSerializerField(read_only=True,
        source='current_version.releasenotes')
    resource_uri = serializers.HyperlinkedIdentityField(view_name='app-detail')
    slug = serializers.CharField(source='app_slug', required=False)
    status = serializers.IntegerField(read_only=True)
    support_email = TranslationSerializerField(required=False)

    support_url = TranslationSerializerField(required=False)
    supported_locales = serializers.SerializerMethodField(
        'get_supported_locales')
    tags = serializers.SerializerMethodField('get_tags')
    upsell = serializers.SerializerMethodField('get_upsell')
    upsold = serializers.HyperlinkedRelatedField(
        view_name='app-detail', source='upsold.free',
        required=False, queryset=Webapp.objects.all())
    user = serializers.SerializerMethodField('get_user_info')
    versions = serializers.SerializerMethodField('get_versions')
    weekly_downloads = serializers.SerializerMethodField(
        'get_weekly_downloads')

    class Meta:
        model = Webapp
        fields = [
            'app_type', 'author', 'banner_message', 'banner_regions',
            'categories', 'content_ratings', 'created', 'current_version',
            'default_locale', 'description', 'device_types', 'homepage',
            'icons', 'id', 'is_offline', 'is_packaged', 'manifest_url',
            'name', 'package_path', 'payment_account', 'payment_required',
            'premium_type', 'previews', 'price', 'price_locale',
            'privacy_policy', 'public_stats', 'release_notes', 'ratings',
            'regions', 'resource_uri', 'slug', 'status', 'support_email',
            'support_url', 'supported_locales', 'tags', 'upsell', 'upsold',
            'user', 'versions', 'weekly_downloads'
        ]

    def _get_region_id(self):
        request = self.context.get('request')
        REGION = getattr(request, 'REGION', None)
        return REGION.id if REGION else None

    def _get_region_slug(self):
        request = self.context.get('request')
        REGION = getattr(request, 'REGION', None)
        return REGION.slug if REGION else None

    def get_content_ratings(self, app):
        body = mkt.regions.REGION_TO_RATINGS_BODY().get(
            self._get_region_slug(), 'generic')
        return {
            'body': body,
            'rating': app.get_content_ratings_by_body().get(body, None),
            'descriptors': app.get_descriptors_dehydrated().get(body, []),
            'interactives': app.get_interactives_dehydrated(),
        }

    def get_icons(self, app):
        return dict([(icon_size, app.get_icon_url(icon_size))
                     for icon_size in amo.APP_ICON_SIZES])

    def get_payment_account(self, app):

        # Avoid a query for payment_account if the app is not premium.
        if not app.is_premium():
            return None

        try:
            # This is a soon to be deprecated API property that only
            # returns the Bango account for historic compatibility.
            app_acct = app.payment_account(PROVIDER_BANGO)
            return reverse('payment-account-detail',
                           args=[app_acct.payment_account.pk])
        except app.PayAccountDoesNotExist:
            return None

    def get_payment_required(self, app):
        if app.has_premium():
            tier = app.get_tier()
            return bool(tier and tier.price)
        return False

    def get_price(self, app):
        if app.has_premium():
            region = self._get_region_id()
            if region in app.get_price_region_ids():
                return app.get_price(region=region)
        return None

    def get_price_locale(self, app):
        if app.has_premium():
            region = self._get_region_id()
            if region in app.get_price_region_ids():
                return app.get_price_locale(region=region)
        return None

    def get_ratings_aggregates(self, app):
        return {'average': app.average_rating,
                'count': app.total_reviews}

    def get_supported_locales(self, app):
        locs = getattr(app.current_version, 'supported_locales', '')
        if locs:
            return locs.split(',') if isinstance(locs, basestring) else locs
        else:
            return []

    def get_tags(self, app):
        return [t.tag_text for t in app.tags.all()]

    def get_upsell(self, app):
        upsell = False
        if app.upsell:
            upsell = app.upsell.premium
        # Only return the upsell app if it's public and we are not in an
        # excluded region.
        if (upsell and upsell.is_public() and self._get_region_id()
                not in upsell.get_excluded_region_ids()):
            return {
                'id': upsell.id,
                'app_slug': upsell.app_slug,
                'icon_url': upsell.get_icon_url(128),
                'name': unicode(upsell.name),
                'resource_uri': reverse('app-detail', kwargs={'pk': upsell.pk})
            }
        else:
            return False

    def get_user_info(self, app):
        user = getattr(self.context.get('request'), 'amo_user', None)
        if user:
            return {
                'developed': app.addonuser_set.filter(
                    user=user, role=amo.AUTHOR_ROLE_OWNER).exists(),
                'installed': app.has_installed(user),
                'purchased': app.pk in user.purchase_ids(),
            }

    def get_versions(self, app):
        # Disable transforms, we only need two fields: version and pk.
        # Unfortunately, cache-machine gets in the way so we can't use .only()
        # (.no_transforms() is ignored, defeating the purpose), and we can't
        # use .values() / .values_list() because those aren't cached :(
        return dict((v.version, reverse('version-detail', kwargs={'pk': v.pk}))
                    for v in app.versions.all().no_transforms())

    def get_weekly_downloads(self, app):
        if app.public_stats:
            return app.weekly_downloads

    def validate_categories(self, attrs, source):
        if not attrs.get('categories'):
            raise serializers.ValidationError('This field is required.')
        set_categories = set(attrs[source])
        total = len(set_categories)
        max_cat = amo.MAX_CATEGORIES

        if total > max_cat:
            # L10n: {0} is the number of categories.
            raise serializers.ValidationError(ngettext(
                'You can have only {0} category.',
                'You can have only {0} categories.',
                max_cat).format(max_cat))

        return attrs

    def get_device_types(self, app):
        with no_translation():
            return [n.api_name for n in app.device_types]

    def save_device_types(self, obj, new_types):
        new_types = [amo.DEVICE_LOOKUP[d].id for d in new_types]
        old_types = [x.id for x in obj.device_types]

        added_devices = set(new_types) - set(old_types)
        removed_devices = set(old_types) - set(new_types)

        for d in added_devices:
            obj.addondevicetype_set.create(device_type=d)
        for d in removed_devices:
            obj.addondevicetype_set.filter(device_type=d).delete()

        # Send app to re-review queue if public and new devices are added.
        if added_devices and obj.status in amo.WEBAPPS_APPROVED_STATUSES:
            mark_for_rereview(obj, added_devices, removed_devices)

    def save_categories(self, obj, categories):
        before = set(obj.categories.values_list('id', flat=True))
        # Add new categories.
        to_add = set(c.id for c in categories) - before
        for c in to_add:
            AddonCategory.objects.create(addon=obj, category_id=c)

        # Remove old categories.
        to_remove = before - set(categories)
        for c in to_remove:
            obj.addoncategory_set.filter(category=c).delete()

    def save_upsold(self, obj, upsold):
        current_upsell = obj.upsold
        if upsold and upsold != obj.upsold.free:
            if not current_upsell:
                log.debug('[1@%s] Creating app upsell' % obj.pk)
                current_upsell = AddonUpsell(premium=obj)
            current_upsell.free = upsold
            current_upsell.save()

        elif current_upsell:
            # We're deleting the upsell.
            log.debug('[1@%s] Deleting the app upsell' % obj.pk)
            current_upsell.delete()

    def save_price(self, obj, price):
        premium = obj.premium
        if not premium:
            premium = AddonPremium()
            premium.addon = obj
        premium.price = Price.objects.active().get(price=price)
        premium.save()

    def validate_device_types(self, attrs, source):
        if attrs.get('device_types') is None:
            raise serializers.ValidationError('This field is required.')
        for v in attrs['device_types']:
            if v not in amo.DEVICE_LOOKUP.keys():
                raise serializers.ValidationError(
                    str(v) + ' is not one of the available choices.')
        return attrs

    def validate_price(self, attrs, source):
        if attrs.get('premium_type', None) not in (amo.ADDON_FREE,
                                                   amo.ADDON_FREE_INAPP):
            valid_prices = Price.objects.exclude(
                price='0.00').values_list('price', flat=True)
            price = attrs.get('price')
            if not (price and Decimal(price) in valid_prices):
                raise serializers.ValidationError(
                    'Premium app specified without a valid price. Price can be'
                    ' one of %s.' % (', '.join('"%s"' % str(p)
                                               for p in valid_prices),))
        return attrs

    def restore_object(self, attrs, instance=None):
        # restore_object creates or updates a model instance, during
        # input validation.
        extras = []
        # Upsell bits are handled here because we need to remove it
        # from the attrs dict before deserializing.
        upsold = attrs.pop('upsold.free', None)
        if upsold is not None:
            extras.append((self.save_upsold, upsold))
        price = attrs.pop('price', None)
        if price is not None:
            extras.append((self.save_price, price))
        device_types = attrs['device_types']
        if device_types:
            extras.append((self.save_device_types, device_types))
            del attrs['device_types']
        instance = super(AppSerializer, self).restore_object(
            attrs, instance=instance)
        for f, v in extras:
            f(instance, v)
        return instance

    def save_object(self, obj, **kwargs):
        # this only gets called if validation succeeds.
        m2m = getattr(obj, '_m2m_data', {})
        cats = m2m.pop('categories', None)
        super(AppSerializer, self).save_object(obj, **kwargs)
        # Categories are handled here because we can't look up
        # existing ones until the initial save is done.
        self.save_categories(obj, cats)


class SimpleAppSerializer(AppSerializer):
    """
    App serializer with fewer fields (and fewer db queries as a result).
    Used as a base for FireplaceAppSerializer and CollectionAppSerializer.
    """
    previews = SimplePreviewSerializer(many=True, required=False,
                                       source='all_previews')

    class Meta(AppSerializer.Meta):
        exclude = ['absolute_url', 'app_type', 'categories', 'created',
                   'default_locale', 'package_path', 'payment_account',
                   'supported_locales', 'weekly_downloads', 'upsold', 'tags']
