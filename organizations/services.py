from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Membership, Organization


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