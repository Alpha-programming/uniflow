from .models import Membership, Scope


MANAGE_PEOPLE = "people.manage_scoped"


def can_manage_member(
    *,
    actor_membership_id,
    target_membership_id,
):
    memberships = (
        Membership.objects
        .select_related(
            "user",
            "team",
            "access_profile",
        )
        .filter(
            pk__in=[
                actor_membership_id,
                target_membership_id,
            ],
        )
    )

    members_by_id = {
        str(member.pk): member
        for member in memberships
    }

    actor = members_by_id.get(str(actor_membership_id))
    target = members_by_id.get(str(target_membership_id))

    if actor is None or target is None:
        return False

    if actor.pk == target.pk:
        return False

    if actor.organization_id != target.organization_id:
        return False

    if not actor.is_active or not actor.user.is_active:
        return False

    # Передача владения будет отдельной операцией.
    if target.system_role == Membership.SystemRole.OWNER:
        return False

    if actor.system_role == Membership.SystemRole.OWNER:
        return True

    # Учащиеся не входят в кадровую иерархию.
    if (
        actor.participant_type != Membership.ParticipantType.STAFF
        or target.participant_type != Membership.ParticipantType.STAFF
    ):
        return False

    if actor.rank is None or target.rank is None:
        return False

    if actor.rank >= target.rank:
        return False

    if (
        actor.team_id is None
        or actor.team_id != target.team_id
        or not actor.team.is_active
    ):
        return False

    profile = actor.access_profile

    if (
        profile is None
        or not profile.is_active
        or profile.organization_id != actor.organization_id
        or not isinstance(profile.capabilities, list)
        or MANAGE_PEOPLE not in profile.capabilities
    ):
        return False

    return Scope.objects.filter(
        membership=actor,
        capability=MANAGE_PEOPLE,
        kind=Scope.Kind.TEAM,
        team_id=actor.team_id,
    ).exists()