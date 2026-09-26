from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("info/", views.info_index, name="info"),
    path("info/news/", views.news_list, name="news"),
    path("info/news/<int:pk>/", views.news_detail, name="news_detail"),
    path("info/calendar/", views.calendar_view, name="calendar"),
    path("info/documents/", views.documents, name="documents"),
    path("info/documents/<int:pk>/", views.document_detail, name="document_detail"),
    path("info/documents/<int:pk>/file/", views.document_download, name="document_download"),
    path("info/faq/", views.faq, name="faq"),
    path("privacy/", views.privacy, name="privacy"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read, name="notifications_read"),
    path("notifications/<int:pk>/", views.notification_open, name="notification_open"),
]
