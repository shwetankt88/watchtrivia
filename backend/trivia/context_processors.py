"""Template context available on every page without a view asking for it.

Two things belong here rather than in a view: the request id (so an error page
can tell a user what to quote) and the resolved theme (so `<body>` can be
rendered with the right colour scheme on the first byte instead of flashing
white before JavaScript runs).
"""

from django.conf import settings

THEME_COOKIE = "watchtrivia_theme"
THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


def resolve_theme(request):
    """The theme the page should render with.

    Precedence: the signed-in user's saved preference, then a theme cookie (so
    the choice survives a logout and applies before the profile loads), then
    "system", which leaves the decision to the OS.
    """
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile is not None and profile.theme in THEMES:
            return profile.theme

    cookie = request.COOKIES.get(THEME_COOKIE)
    if cookie in THEMES:
        return cookie
    return THEME_SYSTEM


def app_context(request):
    return {
        "request_id": getattr(request, "request_id", "system"),
        "theme": resolve_theme(request),
        "site_name": "Watchtrivia",
        "sharing_enabled": settings.SHARING_ENABLED,
        "quizzes_per_day": settings.QUIZZES_PER_DAY,
    }
