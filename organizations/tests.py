from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Membership, Organization, Team, JobTitle, Scope
from unittest.mock import patch
from .services import create_organization
from .models import AccessProfile


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