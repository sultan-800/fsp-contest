from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("competitions/", views.competitions, name="competitions"),
    path("competitions/new/", views.competition_edit, name="competition_new"),
    path("competitions/<int:pk>/", views.competition_manage, name="competition"),
    path("competitions/<int:pk>/edit/", views.competition_edit, name="competition_edit"),
    path("competitions/<int:pk>/action/<str:action>/", views.competition_action, name="competition_action"),
    path("competitions/<int:pk>/tasks/new/", views.task_edit, name="task_add"),
    path("competitions/<int:pk>/tasks/<int:tid>/", views.task_edit, name="task_edit"),
    path("competitions/<int:pk>/tasks/<int:tid>/<str:action>/", views.task_action, name="task_action"),
    path("competitions/<int:pk>/participants/add/", views.participant_add, name="participant_add"),
    path("competitions/<int:pk>/participants/<int:rid>/remove/", views.participant_remove, name="participant_remove"),
    path("competitions/<int:pk>/manual-results/", views.manual_results, name="manual_results"),
    path("submissions/", views.submissions, name="submissions"),
    path("submissions/<int:sid>/", views.review, name="review"),
    path("athletes/", views.athletes, name="athletes"),
    path("athletes/<int:uid>/", views.athlete_edit, name="athlete"),
    path("rating/recalculate/", views.rating_recalculate, name="rating_recalculate"),
    path("<str:key>/", views.crud_list, name="crud"),
    path("<str:key>/new/", views.crud_edit, name="crud_new"),
    path("<str:key>/<int:pk>/", views.crud_edit, name="crud_edit"),
    path("<str:key>/<int:pk>/delete/", views.crud_delete, name="crud_delete"),
]
