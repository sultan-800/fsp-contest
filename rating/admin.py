from django.contrib import admin

from .models import RatingHistory


@admin.register(RatingHistory)
class RatingHistoryAdmin(admin.ModelAdmin):
    list_display = ("athlete", "value", "position", "delta", "reason", "created_at")
    list_filter = ("created_at",)
