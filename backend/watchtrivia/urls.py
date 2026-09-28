from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from trivia import auth_views as trivia_auth_views
from trivia import health

urlpatterns = [
    path("admin/", admin.site.urls),

    # Login and logout are declared here rather than taken from
    # django.contrib.auth.urls because both are customised: login counts
    # failures so a public site cannot be brute forced. These come first, so
    # they shadow the identically named paths in the include below, which is
    # still there for password change and reset.
    path(
        "accounts/login/",
        trivia_auth_views.ThrottledLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", trivia_auth_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),

    # Health probes, unauthenticated and outside the app URL namespace so the
    # names stay flat and predictable for whatever platform is probing.
    path("healthz/", health.healthz, name="healthz"),
    path("readyz/", health.readyz, name="readyz"),

    path("", include("trivia.urls")),
]
