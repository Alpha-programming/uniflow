import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.conf import settings


def validate_time_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError(
            "Укажите существующий часовой пояс, например Asia/Tashkent."
        )

CAPABILITIES = frozenset({
    "organization.manage",
    "tasks.assign_work",
    "tasks.assign_learning",
    "tasks.complete_own",
    "tasks.reopen_scoped",
    "tasks.feedback_scoped",
    "people.manage_scoped",
    "people.invite_learners",
    "roles.manage_scoped",
    "announcements.publish_scoped",
    "channels.create_scoped",
    "analytics.read_scoped",
    "audit.read",
})


def validate_capabilities(value):
    if not isinstance(value, list):
        raise ValidationError(
            "Полномочия должны быть списком."
        )

    if any(not isinstance(item, str) for item in value):
        raise ValidationError(
            "Каждое полномочие должно быть строкой."
        )

    if len(value) != len(set(value)):
        raise ValidationError(
            "Полномочия не должны повторяться."
        )

    unknown = set(value) - CAPABILITIES

    if unknown:
        raise ValidationError(
            "Список содержит неизвестные полномочия."
        )


class Organization(models.Model):
    class Locale(models.TextChoices):
        RUSSIAN = "ru", "Русский"
        UZBEK = "uz-Latn", "O‘zbekcha"
        ENGLISH = "en", "English"

    class WorkMode(models.TextChoices):
        ONSITE = "onsite", "Офлайн"
        REMOTE = "remote", "Онлайн"
        HYBRID = "hybrid", "Смешанный"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=200,
    )

    country_code = models.CharField(
        max_length=2,
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{2}$",
                message="Используйте двухбуквенный код страны, например UZ.",
            )
        ],
    )

    time_zone = models.CharField(
        max_length=64,
        validators=[validate_time_zone],
    )

    default_locale = models.CharField(
        max_length=10,
        choices=Locale.choices,
        default=Locale.RUSSIAN,
    )

    work_mode = models.CharField(
        max_length=10,
        choices=WorkMode.choices,
        default=WorkMode.HYBRID,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="organization_version_gte_1",
            ),
        ]

    def __str__(self):
        return self.name

class Team(models.Model):
    class Kind(models.TextChoices):
        DEPARTMENT = "department", "Отдел"
        TEAM = "team", "Команда"
        CLASS = "class", "Класс"
        COURSE = "course", "Учебная группа"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="teams",
    )

    name = models.CharField(
        max_length=200,
    )

    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.TEAM,
    )

    is_active = models.BooleanField(
        default=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="team_unique_name_per_org",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="team_version_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=[
                        "department",
                        "team",
                        "class",
                        "course",
                    ]
                ),
                name="team_kind_valid",
            ),
        ]

    def __str__(self):
        return self.name

class Membership(models.Model):
    class ParticipantType(models.TextChoices):
        STAFF = "staff", "Сотрудник"
        LEARNER = "learner", "Учащийся"

    class SystemRole(models.TextChoices):
        OWNER = "owner", "Владелец"
        MEMBER = "member", "Участник"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="memberships",
        null=True,
        blank=True,
    )

    access_profile = models.ForeignKey(
        "AccessProfile",
        on_delete=models.PROTECT,
        related_name="memberships",
        null=True,
        blank=True,
    )

    job_title = models.ForeignKey(
        "JobTitle",
        on_delete=models.PROTECT,
        related_name="memberships",
        null=True,
        blank=True,
    )

    participant_type = models.CharField(
        max_length=10,
        choices=ParticipantType.choices,
        default=ParticipantType.STAFF,
    )

    system_role = models.CharField(
        max_length=10,
        choices=SystemRole.choices,
        default=SystemRole.MEMBER,
    )

    rank = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="membership_unique_user_per_org",
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(
                    system_role="owner",
                    is_active=True,
                ),
                name="membership_one_active_owner",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="membership_version_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    system_role__in=["owner", "member"],
                ),
                name="membership_system_role_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        participant_type="staff",
                        rank__isnull=False,
                        rank__gte=1,
                        rank__lte=7,
                    )
                    | models.Q(
                        participant_type="learner",
                        rank__isnull=True,
                        system_role="member",
                    )
                ),
                name="membership_participant_rank_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(system_role="owner")
                    | models.Q(
                        participant_type="staff",
                        rank=1,
                        rank__isnull=False,
                    )
                ),
                name="membership_owner_rank_valid",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.team_id:
            team_organization_id = (
                Team.objects.filter(pk=self.team_id)
                .values_list("organization_id", flat=True)
                .first()
            )

            if (
                team_organization_id is not None
                and team_organization_id != self.organization_id
            ):
                errors["team"] = (
                    "Команда должна принадлежать "
                    "той же компании, что и участник."
                )

        if self.access_profile_id:
            profile_organization_id = (
                AccessProfile.objects.filter(
                    pk=self.access_profile_id,
                )
                .values_list("organization_id", flat=True)
                .first()
            )

            if (
                profile_organization_id is not None
                and profile_organization_id != self.organization_id
            ):
                errors["access_profile"] = (
                    "Профиль прав должен принадлежать "
                    "той же компании, что и участник."
                )

        if self.job_title_id:
            title_organization_id = (
                JobTitle.objects.filter(pk=self.job_title_id)
                .values_list("organization_id", flat=True)
                .first()
            )

            if (
                title_organization_id is not None
                and title_organization_id != self.organization_id
            ):
                errors["job_title"] = (
                    "Должность должна принадлежать "
                    "той же компании, что и участник."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user_id} / {self.organization_id}"

class AccessProfile(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="access_profiles",
    )

    name = models.CharField(
        max_length=100,
    )

    capabilities = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_capabilities],
    )

    is_active = models.BooleanField(
        default=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="profile_unique_name_per_org",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="profile_version_gte_1",
            ),
        ]

    def __str__(self):
        return self.name

class JobTitle(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="job_titles",
    )

    name = models.CharField(
        max_length=100,
    )

    is_active = models.BooleanField(
        default=True,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="job_title_unique_name_per_org",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="job_title_version_gte_1",
            ),
        ]

    def __str__(self):
        return self.name

class Scope(models.Model):
    class Kind(models.TextChoices):
        OWN = "own", "Собственные объекты"
        TEAM = "team", "Команда"
        ORGANIZATION = "organization", "Компания"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="scopes",
    )

    capability = models.CharField(
        max_length=64,
        choices=[
            (value, value)
            for value in sorted(CAPABILITIES)
        ],
    )

    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
    )

    team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="access_scopes",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["capability", "kind", "id"]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="team",
                        team__isnull=False,
                    )
                    | models.Q(
                        kind__in=["own", "organization"],
                        team__isnull=True,
                    )
                ),
                name="scope_kind_team_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    capability__in=sorted(CAPABILITIES),
                ),
                name="scope_capability_valid",
            ),
            models.UniqueConstraint(
                fields=["membership", "capability", "team"],
                condition=models.Q(kind="team"),
                name="scope_unique_team_capability",
            ),
            models.UniqueConstraint(
                fields=["membership", "capability", "kind"],
                condition=models.Q(
                    kind__in=["own", "organization"],
                ),
                name="scope_unique_non_team_capability",
            ),
        ]

    def clean(self):
        super().clean()

        if self.membership_id and self.team_id:
            membership_organization_id = (
                Membership.objects.filter(
                    pk=self.membership_id,
                )
                .values_list("organization_id", flat=True)
                .first()
            )

            team_organization_id = (
                Team.objects.filter(pk=self.team_id)
                .values_list("organization_id", flat=True)
                .first()
            )

            if (
                membership_organization_id is not None
                and team_organization_id is not None
                and membership_organization_id
                != team_organization_id
            ):
                raise ValidationError({
                    "team": (
                        "Команда и участник должны "
                        "принадлежать одной компании."
                    ),
                })

    def __str__(self):
        return f"{self.capability}: {self.kind}"