from django.contrib import admin

from .models import Competition, Registration, Result, Submission, Task


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ("order", "title", "max_score")


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("title", "discipline", "level", "start_at", "end_at", "is_published", "results_published")
    inlines = [TaskInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "athlete", "task", "status", "score", "created_at")
    list_filter = ("status", "competition")


admin.site.register(Registration)
admin.site.register(Result)
