"""The liveness and readiness probe.

Two questions a platform asks, answered separately:

* `/healthz/` -- is the process up? No database, no dependencies, so a
  database blip does not get every container killed and restarted.
* `/readyz/` -- can this instance serve a request? Checks the database with a
  trivial query, because a process that cannot reach Postgres is up but useless.

Both are unauthenticated, so they expose nothing: booleans and a version.
"""

import logging
import os

from django.db import connections
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from trivia import __version__

logger = logging.getLogger("trivia.health")


def _database_ok():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, None
    except Exception as exc:  # noqa: BLE001 - the point is to catch everything
        return False, type(exc).__name__


@never_cache
@csrf_exempt
@require_GET
def healthz(request):
    """Liveness. Always 200 unless the process itself is broken."""
    return JsonResponse(
        {
            "status": "ok",
            "version": __version__,
            "pid": os.getpid(),
        }
    )


@never_cache
@csrf_exempt
@require_GET
def readyz(request):
    """Readiness. 503 when a hard dependency is unusable."""
    db_ok, db_error = _database_ok()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "checks": {"database": "ok" if db_ok else db_error},
    }
    status = 200 if db_ok else 503
    if not db_ok:
        logger.error("readiness check failed", extra={"error": db_error})
    return JsonResponse(payload, status=status)
