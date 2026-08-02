"""NFR-18: list responses paginate at ≤ 20 items with a stable envelope."""

from rest_framework.pagination import PageNumberPagination


class MobilePageNumberPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 20  # the cap is a contract, not a default
    page_size_query_param = "page_size"
