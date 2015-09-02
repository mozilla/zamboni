from django.contrib import admin

from .models import Tag


class TagAdmin(admin.ModelAdmin):
    list_display = ('tag_text', 'created', 'blocked', 'restricted')
    list_editable = ('blocked', 'restricted')
    list_filter = ('blocked', 'restricted')
    ordering = ('-created',)
    search_fields = ('^tag_text',)


admin.site.register(Tag, TagAdmin)
