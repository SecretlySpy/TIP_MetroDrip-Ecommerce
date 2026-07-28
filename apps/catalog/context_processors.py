"""Expose the category taxonomy to every rendered template (C-1)."""

from django.utils.functional import SimpleLazyObject

from .services import get_category_tree


def category_navigation(request):
    """Publish the category tree as `category_nav`.

    Wrapped in SimpleLazyObject so the two catalog queries only run for
    templates that actually render the menu. Without it every admin page, HTMX
    fragment, and error page would pay for navigation it never displays.
    """
    return {"category_nav": SimpleLazyObject(get_category_tree)}
