"""Log formatting that a log drain can actually parse.

Django's default is a human string. On a platform that collects stdout, one
key=value pair per line survives grep, jq and every alerting tool that has been
invented since. In DEBUG we keep the readable format instead, because a
developer staring at a traceback does not want to parse JSON.
"""

import json
import logging
from datetime import datetime, timezone


class RequestIDFilter(logging.Filter):
    """Put the current request id on every record.

    The id is stored in a contextvar by RequestIDMiddleware, so a log line
    emitted from a background thread or a signal handler still gets one
    (as "system" if there is no request).
    """

    def filter(self, record):
        from .middleware import get_request_id

        record.request_id = get_request_id()
        return True


# Attributes LogRecord always carries and that we never want to print twice.
_RESERVED = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()
) | {"asctime", "message", "request_id", "taskName"}


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "system"),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = repr(value)
            payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=str)
