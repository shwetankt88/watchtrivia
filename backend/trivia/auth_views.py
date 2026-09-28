"""The public front door: landing page, signup, login and the user's dashboard.

These are kept apart from `views.py` because they are the only pages a stranger
sees before they have an account, and they carry the two things a public site
needs that the quiz flow does not: spam friction on signup, and a brute-force
stop on login.
"""

import logging

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from trivia.services.quota import status_for
from trivia.services.stats import full_dashboard

from .forms import LoginForm, SignupForm

logger = logging.getLogger("trivia.auth")


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------


@never_cache
def landing(request):
    """The page every visitor arrives on.

    Anonymous visitors get the pitch and a signup button; a signed-in visitor is
    sent straight to their dashboard, because making them click through a
    marketing page to reach their own quizzes would be silly.
    """
    if request.user.is_authenticated:
        return redirect("trivia:dashboard")
    return render(request, "trivia/landing.html", {
        "mock_llm": settings.WATCHTRIVIA_MOCK_LLM,
        "has_api_key": bool(settings.ANTHROPIC_API_KEY),
    })


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def signup(request):
    """Create an account and sign the new user straight in.

    No email confirmation. Confirming an address before someone can try the
    product is the single most effective way to lose signups, and the cost of
    not confirming is one unwanted account -- which the quotas already bound.
    """
    if request.user.is_authenticated:
        return redirect("trivia:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(_safe_next(request, "trivia:dashboard"))
    else:
        form = SignupForm()

    return render(request, "registration/signup.html", {"form": form})


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def _client_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or None


def _login_cache_keys(request, username):
    """Counters shared by every worker, keyed on IP and on account name.

    Two keys because they fail differently: an IP counter stops one host
    spraying many accounts, and an account counter stops a botnet walking one
    account. A successful login clears both, so a user who fumbles their own
    password twice is not left rate limited for the rest of the window.
    """
    return (
        f"login:ip:{_client_ip(request)}",
        f"login:user:{username.strip().lower()}" if username else None,
    )


def _login_blocked(request, username):
    limit = settings.LOGIN_ATTEMPTS_LIMIT
    if limit <= 0:
        return False
    window = settings.LOGIN_ATTEMPTS_WINDOW
    for key in _login_cache_keys(request, username):
        if key and cache.get(key) and cache.get(key) >= limit:
            return True
    return False


def _record_failure(request, username):
    limit = settings.LOGIN_ATTEMPTS_LIMIT
    window = settings.LOGIN_ATTEMPTS_WINDOW
    for key in _login_cache_keys(request, username):
        if not key:
            continue
        cache.set(key, cache.get(key) or 0, timeout=window)
        cache.incr(key)
    logger.info(
        "login failed",
        extra={"user": username, "limit": limit},
    )


def _clear_failures(request, username):
    for key in _login_cache_keys(request, username):
        if key:
            cache.delete(key)


class ThrottledLoginView(DjangoLoginView):
    """`django.contrib.auth.views.LoginView` with a failure counter attached.

    Subclassing beats wrapping so that `redirect_authenticated_user`,
    `next`-parameter handling and the template name all stay Django's job.
    """

    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and _login_blocked(
            request, request.POST.get("username", "")
        ):
            return render(
                request,
                self.template_name,
                {
                    "form": self.get_form(),
                    "throttled": True,
                    "retry_minutes": max(
                        1, settings.LOGIN_ATTEMPTS_WINDOW // 60
                    ),
                },
                status=429,
            )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        _clear_failures(self.request, form.get_user().get_username())
        return super().form_valid(form)

    def form_invalid(self, form):
        _record_failure(self.request, form.data.get("username", ""))
        return super().form_invalid(form)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@never_cache
def dashboard(request):
    """The signed-in home page: totals, streak, recent attempts, allowances.

    Every number comes from `stats.full_dashboard`, which is one call so a view
    that needed four services would not have to guess whether they agree.
    """
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    data = full_dashboard(request.user)
    data["quota"] = {
        "quiz": status_for(request.user, "quiz"),
        "upload": status_for(request.user, "upload"),
    }
    return render(request, "trivia/dashboard.html", data)


def _safe_next(request, fallback):
    """Only follow a `next` that points back at this site.

    Without the host check, `?next=https://evil.example` turns our own login page
    into an open redirect, which is a ready-made phishing link.
    """
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback
