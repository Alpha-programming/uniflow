from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Membership, Organization
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError as ApiValidationError,
)
from config.errors import VersionConflict
from .models import JobTitle
from .policies import can_manage_member


@transaction.atomic
def create_organization(
    *,
    owner,
    name,
    country_code,
    time_zone,
    default_locale=Organization.Locale.RUSSIAN,
    work_mode=Organization.WorkMode.HYBRID,
):
    if (
        owner.pk is None
        or owner._state.adding
        or not owner.is_active
    ):
        raise ValidationError({
            "owner": "Нужен сохранённый активный пользователь.",
        })

    organization = Organization(
        name=name,
        country_code=country_code,
        time_zone=time_zone,
        default_locale=default_locale,
        work_mode=work_mode,
    )

    organization.full_clean()
    organization.save()

    membership = Membership(
        organization=organization,
        user=owner,
        participant_type=Membership.ParticipantType.STAFF,
        system_role=Membership.SystemRole.OWNER,
        rank=1,
    )

    membership.full_clean()
    membership.save()

    return organization

@transaction.atomic
def change_member_job_title(
    *,
    actor,
    organization_id,
    membership_id,
    job_title_id,
    expected_version,
):
    if (
        not actor.is_authenticated
        or not actor.is_active
    ):
        raise PermissionDenied()

    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise ApiValidationError({
            "expectedVersion": "Укажите положительную целую версию.",
        })

    # Изменения прав и членства будем сериализовать
    # через блокировку компании.
    organization = (
        Organization.objects
        .select_for_update()
        .filter(pk=organization_id)
        .first()
    )

    if organization is None:
        raise NotFound()

    actor_membership = Membership.objects.filter(
        organization=organization,
        user=actor,
        is_active=True,
    ).first()

    if actor_membership is None:
        raise PermissionDenied()

    target = (
        Membership.objects
        .select_for_update()
        .filter(
            pk=membership_id,
            organization=organization,
        )
        .first()
    )

    if target is None:
        raise NotFound()

    if not can_manage_member(
        actor_membership_id=actor_membership.pk,
        target_membership_id=target.pk,
    ):
        raise PermissionDenied()

    if target.version != expected_version:
        raise VersionConflict()

    title = None

    if job_title_id is not None:
        title = JobTitle.objects.filter(
            pk=job_title_id,
            organization=organization,
            is_active=True,
        ).first()

        if title is None:
            raise ApiValidationError({
                "jobTitleId": "Должность недоступна.",
            })

    target.job_title = title
    target.version += 1

    try:
        target.full_clean()
    except ValidationError as exc:
        errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else {"nonFieldErrors": exc.messages}
        )
        raise ApiValidationError(errors) from exc

    target.save(
        update_fields=[
            "job_title",
            "version",
            "updated_at",
        ]
    )

    return target