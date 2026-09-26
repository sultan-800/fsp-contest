from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "ФСП Контест — администрирование"
admin.site.site_title = "ФСП Контест"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("competitions/", include("competitions.urls")),
    path("rating/", include("rating.urls")),
    path("panel/", include("panel.urls")),
]

handler400 = "core.views.error_400"
handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
