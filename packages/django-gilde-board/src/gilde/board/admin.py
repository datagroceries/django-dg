from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from gilde.board.models import Attachment, Column, Comment, Group, Label, Relation, Ticket


class ColumnInline(admin.TabularInline):
    model = Column
    extra = 0


@admin.register(Group)
class GroupAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'slug', 'position')
    inlines = (ColumnInline,)


@admin.register(Ticket)
class TicketAdmin(SimpleHistoryAdmin):
    list_display = ('__str__', 'column', 'assignee', 'size', 'is_blocked', 'closed_at')
    list_filter = ('column__group', 'column__category', 'is_blocked')
    search_fields = ('title',)
    raw_id_fields = ('creator', 'assignee')
    filter_horizontal = ('labels',)


@admin.register(Relation)
class RelationAdmin(SimpleHistoryAdmin):
    list_display = ('source', 'type', 'target')
    raw_id_fields = ('source', 'target')


@admin.register(Comment)
class CommentAdmin(SimpleHistoryAdmin):
    list_display = ('__str__', 'author', 'sets_blocked', 'created_at')
    raw_id_fields = ('ticket', 'author', 'parent')


admin.site.register(Label)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'ticket', 'content_type', 'size', 'uploaded_by', 'uploaded_at')
    raw_id_fields = ('ticket', 'uploaded_by')
