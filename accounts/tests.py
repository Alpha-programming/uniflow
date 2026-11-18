from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import patch
from django.db import OperationalError
from uuid import UUID
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from config.pagination import StandardCursorPagination
from config.errors import VersionConflict
from config.serializers import VersionedMutationSerializer


class CsrfTokenTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("accounts:csrf")

    def test_anonymous_user_can_get_token(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(set(data), {"csrfToken"})
        self.assertIsInstance(data["csrfToken"], str)
        self.assertTrue(data["csrfToken"])

    def test_response_sets_csrf_cookie(self):
        response = self.client.get(self.url)

        self.assertIn("csrftoken", response.cookies)

    def test_response_is_not_cached(self):
        response = self.client.get(self.url)

        self.assertIn(
            "no-store",
            response.headers.get("Cache-Control", ""),
        )

    def test_post_is_not_allowed(self):
        response = self.client.get(self.url)
        token = response.json()["csrfToken"]

        response = self.client.post(
            self.url,
            HTTP_X_CSRF_TOKEN=token,
        )

        self.assertEqual(response.status_code, 405)


class HealthCheckTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "uniflow-backend",
            },
        )

class ReadinessCheckTests(TestCase):
    def test_database_is_available(self):
        response = self.client.get("/readyz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "database": "ok",
            },
        )

    def test_database_failure_returns_503(self):
        with patch(
            "config.views.connection.cursor",
            side_effect=OperationalError("private connection details"),
        ):
            response = self.client.get("/readyz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unavailable"},
        )

class RequestIdTests(TestCase):
    def test_response_contains_valid_request_id(self):
        response = self.client.get("/healthz")

        request_id = response.headers.get("X-Request-ID")

        self.assertIsNotNone(request_id)
        self.assertEqual(str(UUID(request_id)), request_id)

    def test_each_request_has_a_different_id(self):
        first_response = self.client.get("/healthz")
        second_response = self.client.get("/healthz")

        self.assertNotEqual(
            first_response.headers["X-Request-ID"],
            second_response.headers["X-Request-ID"],
        )

    def test_unknown_route_also_has_request_id(self):
        response = self.client.get("/api/v1/unknown")

        self.assertEqual(response.status_code, 404)
        self.assertIn("X-Request-ID", response.headers)

class ApiNotFoundTests(TestCase):
    def test_unknown_api_route_returns_error_envelope(self):
        response = self.client.get("/api/v1/unknown")

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "NOT_FOUND",
                    "messageKey": "errors.not_found",
                    "fieldErrors": [],
                    "requestId": response.headers["X-Request-ID"],
                }
            },
        )

    def test_unknown_api_route_returns_json_in_debug_mode(self):
        with self.settings(DEBUG=True):
            response = self.client.get("/api/v1/unknown")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["code"],
            "NOT_FOUND",
        )

class CsrfFailureTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_missing_csrf_token_returns_json_error(self):
        response = self.client.post(
            reverse("accounts:csrf"),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "FORBIDDEN",
                    "messageKey": "errors.forbidden",
                    "fieldErrors": [],
                    "requestId": response.headers["X-Request-ID"],
                }
            },
        )

    def test_invalid_csrf_token_returns_json_error(self):
        self.client.get(reverse("accounts:csrf"))

        response = self.client.post(
            reverse("accounts:csrf"),
            HTTP_X_CSRF_TOKEN="invalid-token",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"]["code"],
            "FORBIDDEN",
        )

class ApiExceptionTests(TestCase):
    def make_request(self):
        request = APIRequestFactory().get("/api/v1/test")
        request.request_id = "11111111-1111-4111-8111-111111111111"

        return request

    def test_validation_error_returns_422(self):
        class ExampleView(APIView):
            authentication_classes = []
            permission_classes = [AllowAny]

            def get(self, request):
                raise ValidationError({
                    "email": ["Private validation details"],
                })

        response = ExampleView.as_view()(self.make_request())

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.data,
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "messageKey": "errors.validation_error",
                    "fieldErrors": [
                        {
                            "field": "email",
                            "messageKey": "errors.invalid_field",
                        }
                    ],
                    "requestId": (
                        "11111111-1111-4111-8111-111111111111"
                    ),
                }
            },
        )

    def test_permission_denied_returns_403(self):
        class ExampleView(APIView):
            authentication_classes = []
            permission_classes = [AllowAny]

            def get(self, request):
                raise PermissionDenied("Private permission details")

        response = ExampleView.as_view()(self.make_request())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["error"]["code"],
            "FORBIDDEN",
        )
        self.assertNotIn(
            "Private permission details",
            str(response.data),
        )

    def test_unexpected_error_returns_safe_500(self):
        class ExampleView(APIView):
            authentication_classes = []
            permission_classes = [AllowAny]

            def get(self, request):
                raise RuntimeError("secret-database-password")

        with self.assertLogs("config.errors", level="ERROR") as logs:
            response = ExampleView.as_view()(self.make_request())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.data,
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "messageKey": "errors.internal_error",
                    "fieldErrors": [],
                    "requestId": (
                        "11111111-1111-4111-8111-111111111111"
                    ),
                }
            },
        )

        self.assertNotIn(
            "secret-database-password",
            str(response.data),
        )
        self.assertNotIn(
            "secret-database-password",
            str(logs.output),
        )
        self.assertIn(
            "11111111-1111-4111-8111-111111111111",
            str(logs.output),
        )

class ApiAuthenticationTests(TestCase):
    def test_anonymous_request_requires_authentication(self):
        class ProtectedView(APIView):
            def get(self, request):
                return Response({"status": "ok"})

        request = APIRequestFactory().get("/api/v1/test")
        request.request_id = "22222222-2222-4222-8222-222222222222"

        response = ProtectedView.as_view()(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data,
            {
                "error": {
                    "code": "AUTH_REQUIRED",
                    "messageKey": "errors.auth_required",
                    "fieldErrors": [],
                    "requestId": (
                        "22222222-2222-4222-8222-222222222222"
                    ),
                }
            },
        )

    def test_authenticated_session_can_access_protected_view(self):
        from django.contrib.auth import get_user_model
        from django.urls import path

        class ProtectedView(APIView):
            def get(self, request):
                return Response({
                    "userId": str(request.user.pk),
                })

        user = get_user_model().objects.create_user(
            username="session-test-user",
            password="test-only-password-739!",
        )

        test_urls = type(
            "TestUrls",
            (),
            {
                "urlpatterns": [
                    path("protected", ProtectedView.as_view()),
                ]
            },
        )

        with self.settings(ROOT_URLCONF=test_urls):
            self.client.force_login(user)
            response = self.client.get("/protected")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"userId": str(user.pk)},
        )

class PaginationTests(TestCase):
    def make_request(self, **params):
        request = APIRequestFactory().get(
            "/api/v1/test-users",
            params,
        )

        return Request(request)

    def make_paginator(self):
        paginator = StandardCursorPagination()

        # У User дата создания называется date_joined.
        paginator.ordering = ("-date_joined", "-id")

        return paginator

    def test_default_page_size(self):
        paginator = self.make_paginator()

        self.assertEqual(
            paginator.get_page_size(self.make_request()),
            30,
        )

    def test_invalid_limits_are_rejected(self):
        paginator = self.make_paginator()

        for value in ("0", "101", "-1", "abc", "1.5", ""):
            with self.subTest(limit=value):
                with self.assertRaises(ParseError):
                    paginator.get_page_size(
                        self.make_request(limit=value)
                    )

    def test_next_cursor_returns_remaining_records(self):
        User = get_user_model()

        for index in range(3):
            User.objects.create_user(
                username=f"pagination-user-{index}",
            )

        queryset = User.objects.all()
        expected_ids = list(
            queryset.order_by(
                "-date_joined",
                "-id",
            ).values_list("id", flat=True)
        )

        first_paginator = self.make_paginator()
        first_page = first_paginator.paginate_queryset(
            queryset,
            self.make_request(limit=2),
        )

        first_response = first_paginator.get_paginated_response(
            [str(user.pk) for user in first_page]
        )

        cursor = first_response.data["nextCursor"]

        self.assertEqual(len(first_page), 2)
        self.assertIsInstance(cursor, str)
        self.assertTrue(cursor)

        second_paginator = self.make_paginator()
        second_page = second_paginator.paginate_queryset(
            queryset,
            self.make_request(limit=2, cursor=cursor),
        )

        second_response = second_paginator.get_paginated_response(
            [str(user.pk) for user in second_page]
        )

        actual_ids = [
            user.pk
            for user in list(first_page) + list(second_page)
        ]

        self.assertEqual(actual_ids, expected_ids)
        self.assertIsNone(
            second_response.data["nextCursor"]
        )

class VersioningTests(TestCase):
    def test_positive_version_is_accepted(self):
        serializer = VersionedMutationSerializer(
            data={"expectedVersion": 1},
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["expectedVersion"],
            1,
        )

    def test_missing_or_invalid_version_is_rejected(self):
        invalid_inputs = [
            {},
            {"expectedVersion": None},
            {"expectedVersion": 0},
            {"expectedVersion": -1},
            {"expectedVersion": "invalid"},
            {"expectedVersion": 1.5},
        ]

        for data in invalid_inputs:
            with self.subTest(data=data):
                serializer = VersionedMutationSerializer(
                    data=data,
                )

                self.assertFalse(serializer.is_valid())
                self.assertIn(
                    "expectedVersion",
                    serializer.errors,
                )

    def test_version_conflict_returns_409(self):
        class ExampleView(APIView):
            authentication_classes = []
            permission_classes = [AllowAny]

            def get(self, request):
                raise VersionConflict()

        request = APIRequestFactory().get("/api/v1/test")
        request.request_id = "33333333-3333-4333-8333-333333333333"

        response = ExampleView.as_view()(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data,
            {
                "error": {
                    "code": "VERSION_CONFLICT",
                    "messageKey": "errors.version_conflict",
                    "fieldErrors": [],
                    "requestId": (
                        "33333333-3333-4333-8333-333333333333"
                    ),
                }
            },
        )