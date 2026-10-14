from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    # Secure download (permission checked)
    path(
        "<int:pk>/download/",
        views.HRDocumentDownloadView.as_view(),
        name="download",
    ),
    # HR
    path("", views.DocumentListView.as_view(), name="list"),
    path("new/", views.DocumentCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.DocumentUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.DocumentDeleteView.as_view(), name="delete"),
    path("legal/", views.LegalListView.as_view(), name="legal"),
    path("legal/new/", views.LegalCreateView.as_view(), name="legal_create"),
    path(
        "legal/<int:pk>/edit/",
        views.LegalUpdateView.as_view(),
        name="legal_edit",
    ),
    # Employee
    path("me/documents/", views.MyDocumentsView.as_view(), name="my_documents"),
    path(
        "me/communications/",
        views.MyCommunicationsView.as_view(),
        name="my_communications",
    ),
]
