from django.contrib import admin

from . import models


class WebappAdmin(admin.ModelAdmin):
    exclude = ('authors',)
    list_display = ('__unicode__', 'status', 'average_rating',
                    'premium_type', 'premium')
    list_filter = ('status', )

    fieldsets = (
        (None, {
            'fields': ('name', 'guid', 'default_locale', 'status',
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
            'fields': ('average_rating', 'bayesian_rating', 'total_reviews'),
        }),
        ('Truthiness', {
            'fields': ('disabled_by_user', 'public_stats'),
        }),
    )

    def get_queryset(self, request):
        return models.Webapp.objects.all()


admin.site.register(models.Webapp, WebappAdmin)
