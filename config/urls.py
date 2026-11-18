from django.contrib import admin
from django.urls import include, path

from .views import health_check, readiness_check


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", health_check, name="health-check"),
    path("readyz", readiness_check, name="readiness-check"),
    path("api/v1/auth/", include("accounts.urls")),
]