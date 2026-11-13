from django.urls import include, path

urlpatterns = [
    path("", include("tvplataforma.urls")),
    path("med/", include("tresvizo_med.urls")),
]
