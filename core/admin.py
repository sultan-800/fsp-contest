from django.contrib import admin

from .models import FAQ, CompetitionLevel, Discipline, Document, News, Notification, Qualification

for m in (Discipline, CompetitionLevel, Qualification, FAQ, Notification):
    admin.site.register(m)


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ("title", "tag", "is_published", "published_at")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_published")
