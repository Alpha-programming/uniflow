from django.urls import path

from .views import csrf_token


app_name = "accounts"

urlpatterns = [
    path("csrf", csrf_token, name="csrf"),
]