from django.urls import path

from . import views

app_name = "competitions"

urlpatterns = [
    path("", views.competition_list, name="list"),
    path("<int:pk>/", views.competition_detail, name="detail"),
    path("<int:pk>/register/", views.register, name="register"),
    path("<int:pk>/unregister/", views.unregister, name="unregister"),
    path("<int:pk>/tasks/<str:letter>/", views.task_view, name="task"),
    path("<int:pk>/tasks/<str:letter>/submit/", views.submit, name="submit"),
    path("<int:pk>/tasks/<str:letter>/attachment/", views.task_attachment, name="task_attachment"),
    path("<int:pk>/results.csv", views.results_csv, name="results_csv"),
    path("<int:pk>/protocol/", views.protocol, name="protocol"),
    path("submissions/<int:sid>/", views.submission_detail, name="submission"),
    path("submissions/<int:sid>/download/", views.submission_download, name="submission_download"),
]
