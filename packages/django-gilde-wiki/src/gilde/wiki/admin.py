from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from gilde.wiki.models import FormerPath, Page


@admin.register(Page)
class PageAdmin(SimpleHistoryAdmin):
    list_display = ('title', 'path', 'updated_at')
    search_fields = ('title', 'path')
    readonly_fields = ('slug', 'path')
    raw_id_fields = ('parent', 'creator')


@admin.register(FormerPath)
class FormerPathAdmin(admin.ModelAdmin):
    list_display = ('path', 'page')
    search_fields = ('path',)
    raw_id_fields = ('page',)
