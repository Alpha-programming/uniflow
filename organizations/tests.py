from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Membership, Organization, Team, JobTitle, Scope
from unittest.mock import patch
from .services import create_organization
from .models import AccessProfile
from .policies import can_manage_member
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as ApiValidationError,
)
from config.errors import VersionConflict
from .services import change_member_job_title


class MembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.user = User.objects.create_user(
            username="member-test",
        )

        cls.second_user = User.objects.create_user(
            username="second-member-test",
        )

        cls.organization = Organization.objects.create(
            name="Uniflow Test",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.other_organization = Organization.objects.create(
            name="Other Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.team = Team.objects.create(
            organization=cls.organization,
            name="Development",
        )

        cls.other_team = Team.objects.create(
            organization=cls.other_organization,
            name="Development",
        )

    def test_staff_membership_is_valid(self):
        membership = Membership(
            organization=self.organization,
            user=self.user,
            team=self.team,
            participant_type="staff",
            rank=3,
        )

        membership.full_clean()
        membership.save()

        self.assertIsNotNone(membership.pk)

    def test_learner_without_rank_is_valid(self):
        membership = Membership(
            organization=self.organization,
            user=self.user,
            participant_type="learner",
            rank=None,
        )

        membership.full_clean()
        membership.save()

        self.assertEqual(membership.system_role, "member")

    def test_duplicate_membership_is_rejected(self):
        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            rank=3,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    organization=self.organization,
                    user=self.user,
                    rank=4,
                )

    def test_same_user_can_join_another_organization(self):
        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            rank=3,
        )

        Membership.objects.create(
            organization=self.other_organization,
            user=self.user,
            rank=5,
        )

        self.assertEqual(
            Membership.objects.filter(user=self.user).count(),
            2,
        )

    def test_second_active_owner_is_rejected(self):
        Membership.objects.create(
            organization=self.organization,
            user=self.user,
            system_role="owner",
            rank=1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    organization=self.organization,
                    user=self.second_user,
                    system_role="owner",
                    rank=1,
                )

    def test_invalid_staff_ranks_are_rejected(self):
        for rank in (None, 0, 8):
            with self.subTest(rank=rank):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Membership.objects.create(
                            organization=self.organization,
                            user=self.user,
                            participant_type="staff",
                            rank=rank,
                        )

    def test_learner_cannot_have_staff_rank(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    organization=self.organization,
                    user=self.user,
                    participant_type="learner",
                    rank=7,
                )

    def test_owner_must_have_rank_one(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Membership.objects.create(
                    organization=self.organization,
                    user=self.user,
                    system_role="owner",
                    rank=2,
                )

    def test_team_from_another_company_is_rejected(self):
        membership = Membership(
            organization=self.organization,
            user=self.user,
            team=self.other_team,
            rank=3,
        )

        with self.assertRaises(ValidationError) as error:
            membership.full_clean()

        self.assertIn("team", error.exception.message_dict)

class CreateOrganizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="company-owner",
        )

    def create_company(self, **overrides):
        data = {
            "owner": self.user,
            "name": "Global Technology",
            "country_code": "UZ",
            "time_zone": "Asia/Tashkent",
        }
        data.update(overrides)

        return create_organization(**data)

    def test_company_is_created_with_owner(self):
        organization = self.create_company()

        membership = Membership.objects.get(
            organization=organization,
        )

        self.assertEqual(membership.user_id, self.user.pk)
        self.assertEqual(membership.system_role, "owner")
        self.assertEqual(membership.participant_type, "staff")
        self.assertEqual(membership.rank, 1)
        self.assertTrue(membership.is_active)

    def test_invalid_company_is_not_saved(self):
        with self.assertRaises(ValidationError):
            self.create_company(
                time_zone="Invalid/TimeZone",
            )

        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

    def test_owner_failure_rolls_back_company(self):
        with patch(
            "organizations.services.Membership.save",
            side_effect=ValidationError(
                "Simulated membership failure"
            ),
        ):
            with self.assertRaises(ValidationError):
                self.create_company()

        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

    def test_inactive_user_cannot_create_company(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self.create_company()

        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

class AccessProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="profile-test-user",
        )

        cls.organization = Organization.objects.create(
            name="First Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.other_organization = Organization.objects.create(
            name="Second Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

    def test_valid_profile_can_be_assigned(self):
        profile = AccessProfile(
            organization=self.organization,
            name="Employee",
            capabilities=["tasks.complete_own"],
        )
        profile.full_clean()
        profile.save()

        membership = Membership(
            organization=self.organization,
            user=self.user,
            rank=3,
            access_profile=profile,
        )
        membership.full_clean()
        membership.save()

        self.assertEqual(
            membership.access_profile_id,
            profile.pk,
        )

    def test_profile_from_another_company_is_rejected(self):
        profile = AccessProfile.objects.create(
            organization=self.other_organization,
            name="Employee",
            capabilities=["tasks.complete_own"],
        )

        membership = Membership(
            organization=self.organization,
            user=self.user,
            rank=3,
            access_profile=profile,
        )

        with self.assertRaises(ValidationError) as error:
            membership.full_clean()

        self.assertIn(
            "access_profile",
            error.exception.message_dict,
        )

    def test_invalid_capabilities_are_rejected(self):
        invalid_values = [
            "tasks.complete_own",
            [123],
            ["unknown.permission"],
            ["tasks.complete_own", "tasks.complete_own"],
        ]

        for capabilities in invalid_values:
            with self.subTest(capabilities=capabilities):
                profile = AccessProfile(
                    organization=self.organization,
                    name="Invalid Profile",
                    capabilities=capabilities,
                )

                with self.assertRaises(ValidationError):
                    profile.full_clean()

    def test_empty_profile_is_valid(self):
        profile = AccessProfile(
            organization=self.organization,
            name="No Permissions",
            capabilities=[],
        )

        profile.full_clean()
        profile.save()

        self.assertEqual(profile.capabilities, [])

class JobTitleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="job-title-test-user",
        )

        cls.organization = Organization.objects.create(
            name="First Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.other_organization = Organization.objects.create(
            name="Second Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

    def test_title_does_not_change_rank_or_permissions(self):
        profile = AccessProfile.objects.create(
            organization=self.organization,
            name="Employee",
            capabilities=["tasks.complete_own"],
        )

        membership = Membership.objects.create(
            organization=self.organization,
            user=self.user,
            rank=5,
            access_profile=profile,
        )

        title = JobTitle.objects.create(
            organization=self.organization,
            name="Director",
        )

        membership.job_title = title
        membership.full_clean()
        membership.save(update_fields=["job_title"])
        membership.refresh_from_db()
        profile.refresh_from_db()

        self.assertEqual(membership.rank, 5)
        self.assertEqual(membership.system_role, "member")
        self.assertEqual(membership.access_profile_id, profile.pk)
        self.assertEqual(
            profile.capabilities,
            ["tasks.complete_own"],
        )

    def test_title_from_another_company_is_rejected(self):
        title = JobTitle.objects.create(
            organization=self.other_organization,
            name="Doctor",
        )

        membership = Membership(
            organization=self.organization,
            user=self.user,
            rank=3,
            job_title=title,
        )

        with self.assertRaises(ValidationError) as error:
            membership.full_clean()

        self.assertIn(
            "job_title",
            error.exception.message_dict,
        )

    def test_duplicate_title_in_same_company_is_rejected(self):
        JobTitle.objects.create(
            organization=self.organization,
            name="Designer",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                JobTitle.objects.create(
                    organization=self.organization,
                    name="Designer",
                )

    def test_same_title_in_different_companies_is_allowed(self):
        for organization in (
            self.organization,
            self.other_organization,
        ):
            JobTitle.objects.create(
                organization=organization,
                name="Designer",
            )

        self.assertEqual(
            JobTitle.objects.filter(name="Designer").count(),
            2,
        )

class ScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(
            username="scope-test-user",
        )

        cls.organization = Organization.objects.create(
            name="Scope Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        other_organization = Organization.objects.create(
            name="Other Scope Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.team = Team.objects.create(
            organization=cls.organization,
            name="Development",
        )

        cls.other_team = Team.objects.create(
            organization=other_organization,
            name="Marketing",
        )

        cls.membership = Membership.objects.create(
            organization=cls.organization,
            user=user,
            team=cls.team,
            rank=3,
        )

    def test_team_scope_is_valid(self):
        scope = Scope(
            membership=self.membership,
            capability="tasks.assign_work",
            kind="team",
            team=self.team,
        )

        scope.full_clean()
        scope.save()

        self.assertTrue(
            Scope.objects.filter(pk=scope.pk).exists()
        )

    def test_team_from_another_company_is_rejected(self):
        scope = Scope(
            membership=self.membership,
            capability="tasks.assign_work",
            kind="team",
            team=self.other_team,
        )

        with self.assertRaises(ValidationError) as error:
            scope.full_clean()

        self.assertIn("team", error.exception.message_dict)

    def test_invalid_kind_team_combinations_are_rejected(self):
        invalid_inputs = [
            {"kind": "team", "team": None},
            {"kind": "own", "team": self.team},
            {"kind": "organization", "team": self.team},
        ]

        for data in invalid_inputs:
            with self.subTest(kind=data["kind"]):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Scope.objects.create(
                            membership=self.membership,
                            capability="tasks.assign_work",
                            **data,
                        )

    def test_duplicate_team_scope_is_rejected(self):
        data = {
            "membership": self.membership,
            "capability": "tasks.assign_work",
            "kind": "team",
            "team": self.team,
        }

        Scope.objects.create(**data)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Scope.objects.create(**data)

class ManageMemberPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.organization = Organization.objects.create(
            name="Policy Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.team = Team.objects.create(
            organization=cls.organization,
            name="Development",
        )

        cls.other_team = Team.objects.create(
            organization=cls.organization,
            name="Design",
        )

        cls.profile = AccessProfile.objects.create(
            organization=cls.organization,
            name="Manager",
            capabilities=["people.manage_scoped"],
        )

        cls.owner = Membership.objects.create(
            organization=cls.organization,
            user=User.objects.create_user(
                username="policy-owner",
            ),
            system_role="owner",
            rank=1,
        )

        cls.manager = Membership.objects.create(
            organization=cls.organization,
            user=User.objects.create_user(
                username="policy-manager",
            ),
            team=cls.team,
            access_profile=cls.profile,
            rank=2,
        )

        cls.employee = Membership.objects.create(
            organization=cls.organization,
            user=User.objects.create_user(
                username="policy-employee",
            ),
            team=cls.team,
            rank=3,
        )

        Scope.objects.create(
            membership=cls.manager,
            capability="people.manage_scoped",
            kind="team",
            team=cls.team,
        )

    def allowed(self, actor, target):
        return can_manage_member(
            actor_membership_id=actor.pk,
            target_membership_id=target.pk,
        )

    def test_owner_can_manage_company_member(self):
        self.assertTrue(
            self.allowed(self.owner, self.employee)
        )

    def test_cross_company_access_is_denied(self):
        other_organization = Organization.objects.create(
            name="External Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        self.employee.organization = other_organization
        self.employee.team = None
        self.employee.save(
            update_fields=["organization", "team"],
        )

        self.assertFalse(
            self.allowed(self.owner, self.employee)
        )
        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

    def test_manager_can_manage_lower_rank_in_own_team(self):
        self.assertTrue(
            self.allowed(self.manager, self.employee)
        )

    def test_equal_and_higher_ranks_are_denied(self):
        for rank in (1, 2):
            with self.subTest(rank=rank):
                self.employee.rank = rank
                self.employee.save(update_fields=["rank"])

                self.assertFalse(
                    self.allowed(self.manager, self.employee)
                )

    def test_other_team_is_denied(self):
        self.employee.team = self.other_team
        self.employee.save(update_fields=["team"])

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

    def test_self_management_is_denied(self):
        self.assertFalse(
            self.allowed(self.manager, self.manager)
        )
        self.assertFalse(
            self.allowed(self.owner, self.owner)
        )

    def test_profile_and_scope_are_both_required(self):
        self.profile.is_active = False
        self.profile.save(update_fields=["is_active"])

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

        self.profile.is_active = True
        self.profile.capabilities = []
        self.profile.save(
            update_fields=["is_active", "capabilities"],
        )

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

        self.profile.capabilities = ["people.manage_scoped"]
        self.profile.save(update_fields=["capabilities"])

        self.manager.scopes.all().delete()

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

    def test_learner_is_not_a_lower_rank_employee(self):
        self.employee.participant_type = "learner"
        self.employee.rank = None
        self.employee.save(
            update_fields=["participant_type", "rank"],
        )

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )
        self.assertTrue(
            self.allowed(self.owner, self.employee)
        )

    def test_inactive_actor_is_denied(self):
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        self.assertFalse(
            self.allowed(self.manager, self.employee)
        )

class ChangeMemberJobTitleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.owner_user = User.objects.create_user(
            username="title-change-owner",
        )

        cls.organization = create_organization(
            owner=cls.owner_user,
            name="Title Change Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        cls.employee = Membership.objects.create(
            organization=cls.organization,
            user=User.objects.create_user(
                username="title-change-employee",
            ),
            rank=4,
        )

        cls.title = JobTitle.objects.create(
            organization=cls.organization,
            name="Designer",
        )

    def change_title(self, **overrides):
        data = {
            "actor": self.owner_user,
            "organization_id": self.organization.pk,
            "membership_id": self.employee.pk,
            "job_title_id": self.title.pk,
            "expected_version": 1,
        }
        data.update(overrides)

        return change_member_job_title(**data)

    def test_owner_can_change_title(self):
        result = self.change_title()
        result.refresh_from_db()

        self.assertEqual(result.job_title_id, self.title.pk)
        self.assertEqual(result.version, 2)
        self.assertEqual(result.rank, 4)
        self.assertEqual(result.system_role, "member")
        self.assertIsNone(result.access_profile_id)

    def test_stale_version_does_not_overwrite_changes(self):
        self.change_title()

        with self.assertRaises(VersionConflict):
            self.change_title(job_title_id=None)

        self.employee.refresh_from_db()

        self.assertEqual(
            self.employee.job_title_id,
            self.title.pk,
        )
        self.assertEqual(self.employee.version, 2)

    def test_title_can_be_removed(self):
        self.change_title()

        result = self.change_title(
            job_title_id=None,
            expected_version=2,
        )

        self.assertIsNone(result.job_title_id)
        self.assertEqual(result.version, 3)

    def test_outsider_cannot_change_title(self):
        outsider = get_user_model().objects.create_user(
            username="title-change-outsider",
        )

        with self.assertRaises(PermissionDenied):
            self.change_title(actor=outsider)

        self.employee.refresh_from_db()

        self.assertIsNone(self.employee.job_title_id)
        self.assertEqual(self.employee.version, 1)

    def test_inactive_title_is_rejected(self):
        self.title.is_active = False
        self.title.save(update_fields=["is_active"])

        with self.assertRaises(ApiValidationError):
            self.change_title()

        self.employee.refresh_from_db()

        self.assertIsNone(self.employee.job_title_id)
        self.assertEqual(self.employee.version, 1)

    def test_title_from_another_company_is_rejected(self):
        other_organization = Organization.objects.create(
            name="External Title Company",
            country_code="UZ",
            time_zone="Asia/Tashkent",
        )

        foreign_title = JobTitle.objects.create(
            organization=other_organization,
            name="External Director",
        )

        with self.assertRaises(ApiValidationError):
            self.change_title(
                job_title_id=foreign_title.pk,
            )

        self.employee.refresh_from_db()

        self.assertIsNone(self.employee.job_title_id)
        self.assertEqual(self.employee.version, 1)

    def test_manager_needs_scope_to_change_title(self):
        team = Team.objects.create(
            organization=self.organization,
            name="Design Team",
        )

        profile = AccessProfile.objects.create(
            organization=self.organization,
            name="Design Manager",
            capabilities=["people.manage_scoped"],
        )

        manager_user = get_user_model().objects.create_user(
            username="title-change-manager",
        )

        manager = Membership.objects.create(
            organization=self.organization,
            user=manager_user,
            team=team,
            rank=2,
            access_profile=profile,
        )

        self.employee.team = team
        self.employee.save(update_fields=["team"])

        # Одного профиля недостаточно: область ещё не выдана.
        with self.assertRaises(PermissionDenied):
            self.change_title(actor=manager_user)

        self.employee.refresh_from_db()

        self.assertIsNone(self.employee.job_title_id)
        self.assertEqual(self.employee.version, 1)

        Scope.objects.create(
            membership=manager,
            capability="people.manage_scoped",
            kind="team",
            team=team,
        )

        result = self.change_title(actor=manager_user)

        self.assertEqual(result.job_title_id, self.title.pk)
        self.assertEqual(result.version, 2)

        # После отзыва области следующие изменения запрещены.
        manager.scopes.all().delete()

        with self.assertRaises(PermissionDenied):
            self.change_title(
                actor=manager_user,
                job_title_id=None,
                expected_version=2,
            )

        self.employee.refresh_from_db()

        self.assertEqual(
            self.employee.job_title_id,
            self.title.pk,
        )
        self.assertEqual(self.employee.version, 2)