from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    # HR: projects
    path("", views.ProjectListView.as_view(), name="list"),
    path("new/", views.ProjectCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="update"),
    path("<int:pk>/archive/", views.ProjectArchiveView.as_view(), name="archive"),
    path(
        "<int:pk>/assign/",
        views.ProjectAssignmentCreateView.as_view(),
        name="assign",
    ),
    path(
        "assignments/<int:pk>/remove/",
        views.ProjectAssignmentDeleteView.as_view(),
        name="unassign",
    ),
    # HR: groups
    path("groups/", views.GroupListView.as_view(), name="groups"),
    path("groups/new/", views.GroupCreateView.as_view(), name="group_create"),
    path("groups/<int:pk>/", views.GroupDetailView.as_view(), name="group_detail"),
    path("groups/<int:pk>/edit/", views.GroupUpdateView.as_view(), name="group_edit"),
    path(
        "groups/<int:pk>/members/add/",
        views.GroupMembershipCreateView.as_view(),
        name="group_member_add",
    ),
    path(
        "groups/members/<int:pk>/remove/",
        views.GroupMembershipDeleteView.as_view(),
        name="group_member_remove",
    ),
    # HR: work logs
    path("worklogs/", views.WorkLogReviewListView.as_view(), name="worklog_review"),
    path(
        "worklogs/<int:pk>/review/",
        views.WorkLogReviewDecisionView.as_view(),
        name="worklog_review_decision",
    ),
    # Employee
    path("me/projects/", views.MyProjectsView.as_view(), name="my_projects"),
    path("me/groups/", views.MyGroupsView.as_view(), name="my_groups"),
    path("me/worklogs/", views.MyWorkLogsView.as_view(), name="my_worklogs"),
    path("me/worklogs/new/", views.WorkLogCreateView.as_view(), name="worklog_create"),
    path(
        "me/worklogs/<int:pk>/edit/",
        views.WorkLogUpdateView.as_view(),
        name="worklog_edit",
    ),
]
