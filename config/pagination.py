from urllib.parse import parse_qs, urlsplit

from rest_framework.exceptions import NotFound, ParseError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


class StandardCursorPagination(CursorPagination):
    page_size = 30
    page_size_query_param = "limit"
    max_page_size = 100
    cursor_query_param = "cursor"

    ordering = ("-created_at", "-id")

    def get_page_size(self, request):
        raw_limit = request.query_params.get(
            self.page_size_query_param
        )

        if raw_limit is None:
            return self.page_size

        if (
            not raw_limit.isascii()
            or not raw_limit.isdecimal()
            or len(raw_limit) > 3
        ):
            raise ParseError("Invalid limit")

        limit = int(raw_limit)

        if not 1 <= limit <= self.max_page_size:
            raise ParseError("Invalid limit")

        return limit

    def decode_cursor(self, request):
        try:
            return super().decode_cursor(request)
        except NotFound as exc:
            raise ParseError("Invalid cursor") from exc

    def get_paginated_response(self, data):
        next_link = self.get_next_link()
        next_cursor = None

        if next_link is not None:
            query = parse_qs(urlsplit(next_link).query)
            next_cursor = query[self.cursor_query_param][0]

        return Response({
            "items": data,
            "nextCursor": next_cursor,
        })