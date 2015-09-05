from django.contrib import admin

from mkt.translations.helpers import truncate

from .models import CannedResponse, ReviewerScore


class CannedResponseAdmin(admin.ModelAdmin):
    def truncate_response(obj):
        return truncate(obj.response, 50)
    truncate_response.short_description = 'Response'

    list_display = ('name', truncate_response)


class ReviewerScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'score', 'note_key', 'note', 'created')
    raw_id_fields = ('user', 'webapp')
    fieldsets = (
        (None, {
            'fields': ('user', 'webapp', 'score', 'note'),
        }),
    )
    list_filter = ('note_key',)


admin.site.register(CannedResponse, CannedResponseAdmin)
admin.site.register(ReviewerScore, ReviewerScoreAdmin)
