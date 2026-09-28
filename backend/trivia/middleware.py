"""Cross-cutting request concerns: request ids and timing.

Kept apart from the views so nothing in here needs a database or a template.
"""

import logging
import time
import uuid
from contextvars import ContextVar

logger = logging.getLogger("trivia.request")

_request_id: ContextVar[str] = ContextVar("request_id", default="system")


def get_request_id():
    return _request_id.get()


def new_request_id():
    return uuid.uuid4().hex


class RequestIDMiddleware:
    """Tag each request with an id, echo it back, and log how long it took.

    The id is taken from the inbound `X-Request-ID` when a proxy or load
    balancer already set one, so a trace survives the hop from the edge. It is
    always replaced with a fresh uuid when missing, and a client-supplied value
    is only accepted if it looks like an id: the header ends up in a response,
    and reflected arbitrary text is a header-injection nuisance.
    """

    HEADER = "X-Request-ID"
    TRUSTED_LENGTH = 64

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(self.HEADER, "")
        request_id = (
            incoming
            if 0 < len(incoming) <= self.TRUSTED_LENGTH
            and all(char.isalnum() or char in "-_" for char in incoming)
            else new_request_id()
        )
        token = _request_id.set(request_id)
        request.request_id = request_id

        started = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)

        response[self.HEADER] = request_id
        elapsed_ms = (time.monotonic() - started) * 1000
        request.elapsed_ms = elapsed_ms

        # Static assets and health checks are noise at INFO.
        quiet = request.path.startswith("/static/") or request.path == "/healthz/"
        if not quiet:
            log = logger.warning if response.status_code >= 500 else logger.info
            log(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "ms": round(elapsed_ms, 2),
                    "user": (
                        request.user.get_username()
                        if getattr(request, "user", None)
                        and request.user.is_authenticated
                        else None
                    ),
                },
            )
        return response
