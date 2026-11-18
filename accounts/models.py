import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Locale(models.TextChoices):
        RUSSIAN = "ru", "Русский"
        UZBEK = "uz-Latn", "O‘zbekcha"
        ENGLISH = "en", "English"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    locale = models.CharField(
        max_length=10,
        choices=Locale.choices,
        default=Locale.RUSSIAN,
    )

    def __str__(self):
        return self.username