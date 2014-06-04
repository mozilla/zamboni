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
                       'highest_status'),
        }),
        ('Details', {
            'fields': ('description', 'homepage', 'privacy_policy',
                       'icon_type'),
        }),
        ('Support', {
            'fields': ('support_url', 'support_email'),
        }),
        ('Stats', {
            'fields': ('average_rating', 'bayesian_rating', 'total_reviews',
                       'weekly_downloads', 'total_downloads'),
        }),
        ('Truthiness', {
            'fields': ('disabled_by_user', 'public_stats'),
        }),
    )

    def queryset(self, request):
        return models.Addon.objects.filter(type__in=amo.MARKETPLACE_TYPES)


class CategoryAdmin(admin.ModelAdmin):
    raw_id_fields = ('addons',)
    list_display = ('name', 'type', 'count')
    list_filter = ('type',)
    exclude = ('count',)


admin.site.register(models.Addon, AddonAdmin)
admin.site.register(models.Category, CategoryAdmin)
