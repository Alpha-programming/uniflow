from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@require_safe
@never_cache
def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "uniflow-backend",
    })


@require_safe
@never_cache
def readiness_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {"status": "unavailable"},
            status=503,
        )

    return JsonResponse({
        "status": "ok",
        "database": "ok",
    })