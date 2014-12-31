from django.contrib import admin

from .models import Tag


class TagAdmin(admin.ModelAdmin):
    list_display = ('tag_text', 'created', 'blocked')
    list_editable = ('blocked',)
    list_filter = ('blocked',)
    ordering = ('-created',)
    search_fields = ('^tag_text',)


admin.site.register(Tag, TagAdmin)
