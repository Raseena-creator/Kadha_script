from django.contrib import admin
from .models import Script, Scene, ScriptElement, Character, ScriptNote, ScriptVersion, ScriptTitlePage, ScriptBackupLog

class ScriptTitlePageInline(admin.StackedInline):
    model = ScriptTitlePage
    can_delete = False
    verbose_name_plural = 'Title Page & Production Metadata'

@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ['title', 'author_name', 'genre', 'script_type', 'language', 'user', 'updated_at']
    list_filter = ['genre', 'script_type', 'language', 'created_at']
    search_fields = ['title', 'description', 'author_name', 'user__username']
    inlines = [ScriptTitlePageInline]

@admin.register(ScriptTitlePage)
class ScriptTitlePageAdmin(admin.ModelAdmin):
    list_display = ['script', 'title', 'author_name', 'draft_revision', 'draft_date', 'updated_at']
    search_fields = ['title', 'author_name', 'pen_name', 'script__title', 'copyright_registration']

@admin.register(ScriptBackupLog)
class ScriptBackupLogAdmin(admin.ModelAdmin):
    list_display = ['script', 'backup_date', 'backup_type', 'status', 'recipient_email', 'filename', 'file_size', 'created_at']
    list_filter = ['status', 'backup_type', 'backup_date']
    search_fields = ['script__title', 'recipient_email', 'filename', 'error_message']
    readonly_fields = ['created_at', 'updated_at']

admin.site.register(Scene)
admin.site.register(ScriptElement)
admin.site.register(Character)
admin.site.register(ScriptNote)
admin.site.register(ScriptVersion)


