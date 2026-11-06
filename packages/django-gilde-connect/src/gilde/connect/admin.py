from django.contrib import admin

from gilde.connect.models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'scopes', 'created_at', 'last_used_at', 'expires_at', 'revoked_at')
    list_filter = ('revoked_at',)
    search_fields = ('name', 'user__email')
    readonly_fields = ('key_hash', 'created_at', 'last_used_at')
    raw_id_fields = ('user',)
