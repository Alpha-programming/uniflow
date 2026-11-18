import uuid

from django.http import JsonResponse

from .errors import error_payload


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())

        response = self.get_response(request)

        response["X-Request-ID"] = request.request_id

        return response


class ApiNotFoundMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        is_api_request = (
            request.path_info == "/api/v1"
            or request.path_info.startswith("/api/v1/")
        )

        is_json_response = (
            response.get("Content-Type", "")
            .split(";", 1)[0]
            .strip()
            == "application/json"
        )

        if (
            is_api_request
            and response.status_code == 404
            and not is_json_response
        ):
            return JsonResponse(
                error_payload(
                    request,
                    code="NOT_FOUND",
                    message_key="errors.not_found",
                ),
                status=404,
            )

        return response