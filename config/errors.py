from django.http import JsonResponse
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    ValidationError,
)
from rest_framework.views import (
    exception_handler as default_exception_handler,
)
import logging
from rest_framework.response import Response

logger = logging.getLogger(__name__)
class VersionConflict(APIException):
    status_code = 409
    default_detail = "Version conflict"
    default_code = "version_conflict"

def error_payload(request, *, code, message_key, field_errors=None):
    return {
        "error": {
            "code": code,
            "messageKey": message_key,
            "fieldErrors": (
                field_errors if field_errors is not None else []
            ),
            "requestId": request.request_id,
        }
    }

def csrf_failure(request, reason=""):
    return JsonResponse(
        error_payload(
            request,
            code="FORBIDDEN",
            message_key="errors.forbidden",
        ),
        status=403,
    )

def collect_field_errors(detail, prefix=""):
    errors = []

    if isinstance(detail, dict):
        for field, value in detail.items():
            field_path = f"{prefix}.{field}" if prefix else str(field)

            errors.extend(
                collect_field_errors(value, field_path)
            )

    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            field_path = prefix

            if isinstance(value, (dict, list)):
                field_path = f"{prefix}.{index}" if prefix else str(index)

            errors.extend(
                collect_field_errors(value, field_path)
            )

    else:
        errors.append({
            "field": prefix or "nonFieldErrors",
            "messageKey": "errors.invalid_field",
        })

    return errors


def api_exception_handler(exc, context):
    response = default_exception_handler(exc, context)

    if response is None:
        request = context["request"]

        logger.error(
            "Unhandled API exception: requestId=%s type=%s",
            request.request_id,
            type(exc).__name__,
        )

        return Response(
            error_payload(
                request,
                code="INTERNAL_ERROR",
                message_key="errors.internal_error",
            ),
            status=500,
        )

    request = context["request"]
    field_errors = []

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        response.status_code = 401
        code = "AUTH_REQUIRED"

    elif isinstance(exc, VersionConflict):
        response.status_code = 409
        code = "VERSION_CONFLICT"

    elif isinstance(exc, ValidationError):
        response.status_code = 422
        code = "VALIDATION_ERROR"
        field_errors = collect_field_errors(exc.detail)

    else:
        code = {
            400: "VALIDATION_ERROR",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            406: "NOT_ACCEPTABLE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            429: "RATE_LIMITED",
        }.get(response.status_code, "INTERNAL_ERROR")

    response.data = error_payload(
        request,
        code=code,
        message_key=f"errors.{code.lower()}",
        field_errors=field_errors,
    )

    return response