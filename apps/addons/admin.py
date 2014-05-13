from django.contrib import admin

import amo

from . import models


class AddonAdmin(admin.ModelAdmin):
    exclude = ('authors',)
    list_display = ('__unicode__', 'type', 'status', 'average_rating',
                    'premium_type', 'premium')
    list_filter = ('type', 'status')

    fieldsets = (
        (None, {
            'fields': ('name', 'guid', 'default_locale', 'type', 'status',
                       'highest_status', 'outstanding'),
        }),
        ('Details', {
            'fields': ('summary', 'description', 'homepage', 'eula',
                       'privacy_policy', 'developer_comments', 'icon_type',
                       'the_reason', 'the_future'),
        }),
        ('Support', {
            'fields': ('support_url', 'support_email'),
        }),
        ('Stats', {
            'fields': ('average_rating', 'bayesian_rating', 'total_reviews',
                       'weekly_downloads', 'total_downloads',
                       'average_daily_downloads', 'average_daily_users',
                       'share_count'),
        }),
        ('Truthiness', {
            'fields': ('disabled_by_user', 'trusted', 'view_source',
                       'public_stats', 'prerelease', 'admin_review',
                       'site_specific', 'external_software', 'dev_agreement'),
        }),
        ('Money', {
            'fields': ('wants_contributions', 'paypal_id', 'suggested_amount',
                       'annoying'),
        }),
        ('Dictionaries', {
            'fields': ('target_locale', 'locale_disambiguation'),
        }))

    def queryset(self, request):
        return models.Addon.objects.filter(type__in=amo.MARKETPLACE_TYPES)


class FeatureAdmin(admin.ModelAdmin):
    raw_id_fields = ('addon',)
    list_filter = ('application', 'locale')
    list_display = ('addon', 'application', 'locale')


class CategoryAdmin(admin.ModelAdmin):
    raw_id_fields = ('addons',)
    list_display = ('name', 'application', 'type', 'count')
    list_filter = ('application', 'type')
    exclude = ('count',)


admin.site.register(models.Feature, FeatureAdmin)
admin.site.register(models.Addon, AddonAdmin)
admin.site.register(models.Category, CategoryAdmin)
